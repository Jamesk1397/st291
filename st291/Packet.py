import bitstring
import json
import copy
from collections import deque
from scte.Scte104.SpliceEvent import SpliceEvent

from st291.ST291_enums import VALS, DID_SDID

class Packet:
    def __init__(self, bitarray_data):
        self.payload_descriptor = ""

        self.values_dict = {
            "C": bitarray_data.read("uint:1"),
            "Line Number": bitarray_data.read("uint:11"),
            "Horizontal Offset": bitarray_data.read("uint:12"),
            "S": bitarray_data.read("uint:1"),
            "StreamNum": bitarray_data.read("uint:7")
        }

        # Offset for parity bits
        self.offset_reader(bitarray_data, 2)
        self.DID = bitarray_data.read("uint:8")

        # Offset for parity bits
        self.offset_reader(bitarray_data, 2)
        self.SDID = bitarray_data.read("uint:8")

        # Offset for parity bits
        self.offset_reader(bitarray_data, 2)
        self.word_count = bitarray_data.read("uint:8")

        self.UDW = self.find_UDW_object(bitarray_data)

        # First bit of checksum word is an inverse bit
        self.offset_reader(bitarray_data, 1)
        self.values_dict["Checksum Word"] = bitarray_data.read("uint:9")

        # UDW_bit_count = self.word_count * 10
        # word_align = 32 - ((UDW_bit_count - 2 + 10) % 32)
        # self.values_dict["Word Align"] = str(len(bitarray_data.read("bin:" + str(word_align)))) + " bits"

        if (self.DID in DID_SDID):
            if self.SDID in DID_SDID[self.DID]:
                self.values_dict["Packet Info"] = DID_SDID[self.DID][self.SDID]
            else:
                self.values_dict["Packet Info"] = DID_SDID[self.DID]
        else:
            self.values_dict["Packet Info"] = ""

    def find_UDW_object(self, bitarray_data):
        if self.is_scte_104_packet():
            UDW_hex = "0x"

            for _ in range(self.word_count):
                self.offset_reader(bitarray_data, 2)
                word = bitarray_data.read("hex:8")
                UDW_hex += word

            self.payload_descriptor = UDW_hex[:4]

            return SpliceEvent(bitstring.BitString("0x" + UDW_hex[4:]))
        else:
            UDW_bit_count = self.word_count * 10
            UDW_int = bitarray_data.read("uint:" + str(UDW_bit_count))
            return UDW_int

    def offset_reader(self, bitarray_data, bit_offset):
        bitarray_data.pos += bit_offset

    def to_dict(self):
        final_dict = copy.deepcopy(self.values_dict)
        final_dict["DID"] = self.DID
        final_dict["SDID"] = self.SDID
        final_dict["Data Count"] = self.word_count

        if isinstance(self.UDW, int):
            final_dict["UDW"] = self.UDW
        else:
            final_dict["UDW"] = self.UDW.to_dict()

        return final_dict

    def to_printable_dict(self):
        printable_dict = copy.deepcopy(self.values_dict)
        printable_dict["DID"] = hex(self.DID)
        printable_dict["SDID"] = hex(self.SDID)
        printable_dict["Data Count"] = self.word_count
        printable_dict["Checksum Word"] = hex(printable_dict["Checksum Word"])

        for title, value in printable_dict.items():
            if title in VALS and value in VALS[title]:
                printable_dict[title] = "(" + str(printable_dict[title]) + ") " + VALS[title][value]

        if isinstance(self.UDW, int):
            printable_dict["UDW"] = self.UDW
        else:
            if self.is_scte_104_packet():
                printable_dict["UDW"] = self.UDW.to_dict(upid_as_str=True)
            else:
                printable_dict["UDW"] = self.UDW.to_dict()
        return printable_dict

    def to_binary(self):
        self.values_dict["Line Number"] = 0x7FF
        self.values_dict["Horizontal Offset"] = 0xFFF
        binary_str = ""

        udw_bin = ""

        if not isinstance(self.UDW, int):
            udw_bit_array = self.UDW.to_binary()
            udw_bit_array.prepend(self.payload_descriptor)
            udw_hex = udw_bit_array.hex
            self.word_count = int(len(udw_hex) / 2)
            udw_bin = self.convert_8_to_10_bit_words(udw_bit_array)
        else:
            udw_bin = self.int_to_bin(self.UDW, self.word_count * 10)
            # udw_bin = self.convert_8_to_10_bit_words(udw_bit_array)

        c = self.values_dict["C"]
        line_num = self.values_dict["Line Number"]
        horiz_offset = self.values_dict["Horizontal Offset"]
        s = self.values_dict["S"]
        stream_num = self.values_dict["StreamNum"]
        checksum = self.values_dict["Checksum Word"]

        binary_str += self.int_to_bin(c, 1)
        binary_str += self.int_to_bin(line_num, 11)
        binary_str += self.int_to_bin(horiz_offset, 12)
        binary_str += self.int_to_bin(s, 1)
        binary_str += self.int_to_bin(stream_num, 7)
        did = self.int_to_bin(self.DID, 8)
        sdid = self.int_to_bin(self.SDID, 8)
        data_count = self.int_to_bin(self.word_count, 8)
        binary_str += self.convert_8_to_10_bit_words(bitstring.BitString(bin=did + sdid + data_count))
        binary_str += udw_bin
        checksum_bin = self.int_to_bin(checksum, 9)
        checksum_parity = "0"

        if checksum_bin[0] == "0":
            checksum_parity = "1"

        binary_str += checksum_parity
        binary_str += checksum_bin

        word_align = 32 - ((self.word_count * 10 - 2 + 10) % 32)
        binary_str += '0' * int(word_align)

        return bitstring.BitString(bin=binary_str)

    def convert_8_to_10_bit_words(self, bitarray):
        raw_binary_str = bitarray.bin

        converted = ""

        word = ""
        num_odd = 0
        for i in raw_binary_str:
            if i == '1':
                num_odd = (num_odd + 1) % 2

            word = word + i

            if len(word) == 8:
                num_even = 0

                if num_odd == 0:
                    num_even = 1

                converted = converted + str(num_even) + str(num_odd) + word
                word = ""
                num_odd = 0

        return converted

    def int_to_bin(self, value, num_bits=1):
        raw = bin(value).lstrip("0b")

        num_missing_bits = num_bits - len(raw)

        raw = "0" * num_missing_bits + raw

        return raw

    def is_scte_104_packet(self):
        return self.DID == 0x41 and self.SDID == 0x07