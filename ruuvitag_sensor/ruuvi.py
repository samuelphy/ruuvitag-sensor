import re
import sys
import os
import time

from ruuvitag_sensor.url_decoder import UrlDecoder

mac_regex = '[0-9a-f]{2}([:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$'

if not sys.platform.startswith('linux') or os.environ.get('CI') == 'True':
    # Use BleCommunicationDummy also for CI as it can't use gattlib
    from ruuvitag_sensor.ble_communication import BleCommunicationDummy
    ble = BleCommunicationDummy()
else:
    from ruuvitag_sensor.ble_communication import BleCommunicationNix
    ble = BleCommunicationNix()


class RunFlag(object):
    """
    Wrapper for boolean run flag

    Attributes:
        running (bool): Defines if function should continue execution
    """

    running = True


# TODO: Split this class to common functions and RuuviTagSensor

class RuuviTagSensor(object):

    def __init__(self, mac):

        if not re.match(mac_regex, mac.lower()):
            raise ValueError('{} is not valid mac address'.format(mac))

        self._mac = mac
        self._state = {}
        self._data = None

    @property
    def mac(self):
        return self._mac

    @property
    def state(self):
        return self._state

    @staticmethod
    def get_data(mac):
        raw = ble.get_data(mac)
        return RuuviTagSensor.convert_data(raw)

    @staticmethod
    def convert_data(raw):
        """
        Convert hexadcimal data to string and validate that data is from RuuviTag.
        Encoded data part is after ruu.vi/# or r/

        Returns:
            string: Encoded sensor data
        """
        try:
            # TODO: Fix conversion so convered data will show https://ruu.vi/# and htts://r/
            # Now it has e.g. [Non_ASCII characters]ruu.vi/#AjwYAMFc
            base16_split = [raw[i:i + 2] for i in range(0, len(raw), 2)]
            selected_hexs = filter(lambda x: int(x, 16) < 128, base16_split)
            characters = [chr(int(c, 16)) for c in selected_hexs]
            data = ''.join(characters)

            # take only part after ruu.vi/# or r/
            index = data.find('ruu.vi/#')
            if index > -1:
                return data[(index + 8):]
            else:
                index = data.find('r/')
                if index > -1:
                    return data[(index + 2):]
                return None
        except:
            return None

    @staticmethod
    def find_ruuvitags():
        """
        Find all RuuviTags. Function will print the mac and the state of the sensors when found.
        Function will execute as long as it is stopped. Stop ecexution with Crtl+C.

        Returns:
            dict: MAC and state of found sensors
        """

        print('Finding RuuviTags. Stop with Ctrl+C.')

        datas = dict()

        for new_data in RuuviTagSensor._get_ruuvitag_datas():
            if new_data[0] in datas:
                continue
            datas[new_data[0]] = new_data[1]
            print(new_data[0])
            print(new_data[1])

        return datas

    @staticmethod
    def get_data_for_sensors(macs=[], search_duratio_sec=5):
        """
        Get lates data for sensors in the MAC's list.

        Args:
            macs (array): MAC addresses
            search_duratio_sec (int): Search duration in seconds. Default 5.
        Returns:
            dict: MAC and state of found sensors
        """

        print('Get latest data for sensors. Stop with Ctrl+C.')
        print('Stops automatically in {}s'.format(search_duratio_sec))
        print('MACs: {}'.format(macs))

        datas = dict()

        for new_data in RuuviTagSensor._get_ruuvitag_datas(macs, search_duratio_sec):
            datas[new_data[0]] = new_data[1]

        return datas

    @staticmethod
    def get_datas(callback, macs=[], run_flag=RunFlag()):
        """
        Get data for all ruuvitag sensors or sensors in the MAC's list.

        Args:
            callback (func): callback funcion to be called when new data is received
            macs (list): MAC addresses
            run_flag (object): RunFlag object. Function executes while run_flag.running
        """

        print('Get latest data for sensors. Stop with Ctrl+C.')
        print('MACs: {}'.format(macs))

        for new_data in RuuviTagSensor._get_ruuvitag_datas(macs, None, run_flag):
            callback(new_data)

    def update(self):
        """
        Get lates data from the sensor and update own state.

        Returns:
            dict: Latest state
        """

        data = RuuviTagSensor.get_data(self._mac)

        if data == self._data:
            return self._state

        self._data = data

        if self._data is None:
            self._state = {}
        else:
            self._state = UrlDecoder().decode_data(self._data)

        return self._state

    @staticmethod
    def _get_ruuvitag_datas(macs=[], search_duratio_sec=None, run_flag=RunFlag()):
        """
        Get data from BluetoothCommunication and handle data encoding.

        Args:
            macs (list): MAC addresses. Default empty list.
            search_duratio_sec (int): Search duration in seconds. Default None.
            run_flag (object): RunFlag object. Function executes while run_flag.running. Default new RunFlag.

        Yields:
            tuple: MAC and State of RuuviTag sensor data
        """

        start_time = time.time()
        data_iter = ble.get_datas()

        for ble_data in data_iter:
            # Check duration
            if search_duratio_sec and time.time() - start_time > search_duratio_sec:
                data_iter.send(StopIteration)
                break
            # Check running flag
            if not run_flag.running:
                data_iter.send(StopIteration)
                break
            # Check MAC whitelist
            if macs and not ble_data[0] in macs:
                continue
            encoded = RuuviTagSensor.convert_data(ble_data[1])
            # Check that encoded data is valid RuuviTag data and it is sensor data
            if encoded is not None:
                state = UrlDecoder().decode_data(encoded)
                if state is not None:
                    yield (ble_data[0], state)
