import sys
from serial import Serial
import time

DEBUG = True
VERBOSE = True  # Verbose mode provides more raw EEG updates
DEFAULT_PORT = 'COM3'

MAX_PACKET_LEN = 169
RESET_CODE = b'\x00\xF8\x00\x00\x00\xE0'

def _cb(data):
    print(data)

def mf_parser(packet):
    # See the MindSet Communications Protocol
    ret = {}
    # The first byte in the list was packet_len, so start at i = 1 
    i = 1
    while (i < len(packet) - 1):
        code_level = packet[i] if isinstance(packet[i], int) else ord(packet[i])
        # signal quality
        if code_level == 0x02:
            ret['quality'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            i += 2
        # attention
        elif code_level == 0x04:
            ret['attention'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            i += 2
        # meditation
        elif code_level == 0x05:
            ret['meditation'] = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            i += 2
        # EEG power
        elif code_level == 0x83:
            ret['eeg'] = []
            for c in range(i + 1, i + 25, 3):
                v1 = packet[c] if isinstance(packet[c], int) else ord(packet[c])
                v2 = packet[c + 1] if isinstance(packet[c + 1], int) else ord(packet[c + 1])
                v3 = packet[c + 2] if isinstance(packet[c + 2], int) else ord(packet[c + 2])
                ret['eeg'].append(v1 << 16 | v2 << 8 | v3)
            i += 26
        # Raw Wave Value
        elif code_level == 0x80:
            v1 = packet[i + 1] if isinstance(packet[i + 1], int) else ord(packet[i + 1])
            v2 = packet[i + 2] if isinstance(packet[i + 2], int) else ord(packet[i + 2])
            ret['eeg_raw'] = v1 << 8 | v2
            i += 4
    return ret

class MindFlexConnection:
    def __init__(self, port=DEFAULT_PORT, debug=DEBUG, verbose=VERBOSE):
        self.debug = debug
        self.verbose = verbose
        self.ser = Serial(port=port, baudrate=57600)
        if self.debug:
            print('Connection open')
        if self.debug:
            self.received = []

    def close(self):
        if self.ser.isOpen():
            try:
                self.ser.close()
            except Exception as e:
                pass
            print('Connection closed')

    def read(self, callback=_cb):
        # Send RESET_CODE to switch to Mode 2
        self.ser.write(RESET_CODE)
        time.sleep(0.001)  # Short pause after sending RESET_CODE

        prev_byte = b'c'
        in_packet = False
        mode_2_confirmed = False

        try:
            while True:
                cur_byte = self.ser.read(1)

                # Confirm Mode 2 activation
                if not mode_2_confirmed:
                    if cur_byte != b'\xE0':  # If byte is not 224, Mode 2 is enabled
                        print('Mode 2 enabled')
                        mode_2_confirmed = True
                    continue

                # Look for the start of the packet
                if not in_packet and prev_byte == b'\xAA' and cur_byte == b'\xAA':
                    in_packet = True
                    packet = []
                    continue

                if in_packet:
                    if len(packet) == 0:
                        if cur_byte == b'\xAA':
                            continue
                        packet_len = cur_byte[0]  # Python 3 bytes are already integers
                        checksum_total = 0
                        packet = [cur_byte[0]]
                        if packet_len >= MAX_PACKET_LEN:
                            print('Packet too long: %s' % packet_len)
                            in_packet = False
                            continue
                    elif len(packet) - 1 == packet_len:
                        packet_checksum = cur_byte[0]
                        in_packet = False
                        if (~(checksum_total & 255) & 255) == packet_checksum:
                            try:
                                if self.verbose or packet_len > 4:
                                    ret = mf_parser(packet)
                                    if self.debug:
                                        print(ret)
                                    callback(ret)
                            except Exception as e:
                                print('Could not parse because of %s' % e)
                        else:
                            print('Warning: invalid checksum')
                            print(~(checksum_total & 255) & 255)
                            print(packet_checksum)
                            print(packet)
                            if self.debug:
                                import pdb; pdb.set_trace()
                    else:
                        byte_value = cur_byte[0]
                        checksum_total += byte_value
                        packet.append(byte_value)

                # Keep track of the last byte to catch sync bytes
                prev_byte = cur_byte

        except KeyboardInterrupt:
            self.close()
            if self.debug:
                print('Exiting')
            sys.exit(0)

def get_argparser():
    from argparse import ArgumentParser
    desc = 'Connect to MindFlex via bluetooth'
    prs = ArgumentParser(description=desc)
    prs.add_argument('--port', '-p', default=DEFAULT_PORT)
    prs.add_argument('--debug', action='store_true')
    prs.add_argument('--verbose', '-v', action='store_true')
    return prs

if __name__ == '__main__':
    parser = get_argparser()
    args = parser.parse_args()
    connection = MindFlexConnection(port=args.port, 
                                    debug=args.debug, 
                                    verbose=args.verbose)
    connection.read()