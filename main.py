import serial
import sys
import argparse
import datetime
import time

# Global variable for the output file
output_file = open("mindflex_data.csv", "w")
output_file.write("Timestamp,Data\n")  # Write the CSV header

def print_data(packet):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    packet_str = ','.join([f"{byte}" for byte in packet])
    output_line = f"{timestamp},{packet_str}\n"
    print(output_line, end='')  # Print to console
    output_file.write(output_line)  # Write to file
    
# Constants
DEFAULT_PORT = 'COM8'  # Update this to your HC-06 COM port
BAUD_RATE = 57600  # Update this to your HC-06 baud rate
MAX_PACKET_LEN = 169
RESET_CODE = b'\x00\xF8\x00\x00\x00\xE0'
RECORDING_TIME = 10  # Recording time in seconds

# Parser function with added debug prints
def mf_parser(packet):
    print(f"Parsing packet: {packet}")  # Debugging print
    ret = {}
    i = 1
    while i < len(packet) - 1:
        code_level = packet[i]
        if code_level == 0x02:
            ret['quality'] = packet[i + 1]
            i += 2
        elif code_level == 0x04:
            ret['attention'] = packet[i + 1]
            i += 2
        elif code_level == 0x05:
            ret['meditation'] = packet[i + 1]
            i += 2
        elif code_level == 0x83:
            ret['eeg'] = []
            for c in range(i + 1, i + 25, 3):
                ret['eeg'].append(packet[c] << 16 | packet[c + 1] << 8 | packet[c + 2])
            i += 26
        elif code_level == 0x80:
            ret['eeg_raw'] = packet[i+1] << 8 | packet[i+2]
            i += 4
    return ret

# MindFlex connection class
class MindFlexConnection:
    def __init__(self, port, callback=print_data):
        self.ser = serial.Serial(port=port, baudrate=BAUD_RATE)
        self.callback = callback
        self.start_time = None
        print('Connection open')

    def close(self):
        if self.ser.isOpen():
            try:
                self.ser.close()
            except Exception as e:
                pass
            print('Connection closed')

    def read(self):
        prev_byte = b'c'
        in_packet = False
        packet = []
        try:
            while True:
                cur_byte = self.ser.read(1)
                print(f'Received byte: {cur_byte}')  # Debugging print

                if cur_byte == b'\xAA' and prev_byte == b'\xAA':
                    print('Start of new packet detected')  # Debugging print
                    in_packet = True
                    packet = [cur_byte]
                    continue
                elif in_packet:
                    packet.append(cur_byte)
                    if len(packet) > MAX_PACKET_LEN:
                        print('Packet too long, resetting')  # Debugging print
                        in_packet = False
                        packet = []
                    elif cur_byte == b'\xAA' and packet[-2] == b'\xAA':
                        print('End of packet detected')  # Debugging print
                        self.callback(packet)  # Write the entire packet to file
                        in_packet = False
                        packet = []
                prev_byte = cur_byte
        except KeyboardInterrupt:
            self.close()
            print('Exiting')
            sys.exit(0)


# Command-line argument parser
def get_argparser():
    prs = argparse.ArgumentParser(description='Connect to MindFlex via Bluetooth')
    prs.add_argument('--port', '-p', default=DEFAULT_PORT)
    return prs

if __name__ == '__main__':
    parser = get_argparser()
    args = parser.parse_args()
    try:
        connection = MindFlexConnection(port=args.port)
        connection.read()
    finally:
        output_file.close()