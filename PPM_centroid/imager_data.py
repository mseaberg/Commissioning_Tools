import numpy as np
import pandas as pd
from ophyd import EpicsSignalRO as SignalRO


class DataHandler:
    """
    Class to manage the data being passed between objects, functions
    """
    def __init__(self):
        """
        Method to initialize the data handler class
        """

        # timestamp key
        self.timestamp_key = 'timestamps'

        # keys for data that is calculated on every shot
        self.stripchart_imager_keys = ['cx', 'cy', 'wx', 'wy', 'intensity']

        # keys for wfs data that is calculated on every shot
        self.stripchart_wfs_keys = ['z_x', 'z_y', 'rms_x', 'rms_y']

        # keys for all stripchart data
        self.stripchart_all_keys = self.stripchart_imager_keys + self.stripchart_wfs_keys

        # keys for smoothed data
        self.stripchart_smooth_keys = [key+'_smooth' for key in self.stripchart_all_keys]

        # keys for constants
        self.constant_keys = ['counter', 'pixSize', 'cx_ref', 'cy_ref', 'tx']

        # keys for 1-D coordinates
        self.coord_keys = ['x', 'y']

        # keys for wfs 1-D coordinates
        self.wfs_coord_keys = ['x_prime', 'y_prime', 'xf']

        # keys for 1-D arrays updated every shot
        self.image_array_keys = ['lineout_x', 'lineout_y', 'projection_x',
                           'projection_y', 'fit_x', 'fit_y']

        # keys for 1-D wfs arrays updated every shot
        self.wfs_array_keys = ['x_res', 'y_res', 'focus_horizontal', 'focus_vertical']

        # keys for images updated every shot
        self.image_keys = ['profile']

        # keys for wfs images updated every shot
        self.wfs_image_keys = ['focus', 'F0', 'wave']

        # read file with PV names
        self.filename = '/reg/neh/home/seaberg/Commissioning_Tools/PPM_centroid/epics_pvs.txt'

        # initialize data dictionary
        self.data_dict = {}

        # initialize epics signals
        self.epics_signals = {}

        # set initialized to False until we get an imager
        self.initialized = False

        # initialize PPM_object to None
        self.imager = None

    def initialize(self, PPM_object, N=1024):

        self.imager = PPM_object

        self.N = N
        self.im_N = self.imager.N
        self.im_M = self.imager.M

        # read pv keys
        self.pv_keys = self.read_pv_names()

        # initialize data dictionary entries
        self.reset_data()

        # update target position
        self.update_target()

        self.initialized = True

    def uninitialize(self):
        self.initialized = False

    def update_imager(self, PPM_object):
        self.imager = PPM_object
        self.update_target()

    def update_target(self):
        self.data_dict['cx_ref'] = self.imager.cx_target
        self.data_dict['cy_ref'] = self.imager.cy_target

    def reset_data(self):
        """
        Method to reset the data. This is called when a new imager is selected for instance.
        This should really be cleaned up so that it's easier to add new items to the data dictionary. Basically
        just need to categorize different types of data based on array size in terms of how to initialize them. This
        could be defined in a file.
        """

        # initialize timestamps
        self.data_dict[self.timestamp_key] = np.full(self.N, np.nan, dtype=float)

        # initialize stripchart data to nan's
        for key in self.stripchart_all_keys:
            self.data_dict[key] = np.full(self.N, np.nan, dtype=float)

        # initialize stripchart smoothed data to nan's
        for key in self.stripchart_smooth_keys:
            self.data_dict[key] = np.full(self.N, np.nan, dtype=float)

        # initialize constants to zero
        for key in self.constant_keys:
            self.data_dict[key] = 0.0

        # initialize coordinates
        for key in self.coord_keys:
            self.data_dict[key] = np.linspace(-1024, 1023, 100)

        for key in self.wfs_coord_keys:
            self.data_dict[key] = np.linspace(-1024, 1023, 100)

        # initialize 1D array data
        for key in self.image_array_keys:
            self.data_dict[key] = np.zeros(100)

        for key in self.wfs_array_keys:
            self.data_dict[key] = np.zeros(100)

        # initialize image data
        for key in self.image_keys:
            self.data_dict[key] = np.zeros((self.im_N, self.im_M))

        for key in self.wfs_image_keys:
            self.data_dict[key] = np.zeros((self.im_N, self.im_M))

        # initialize pv data
        for key in self.pv_keys:
            self.data_dict[key] = np.full(self.N, np.nan, dtype=float)

        # update keys that are allowed for plotting
        self.data_dict['key_list'] = ['timestamps','cx', 'cy', 'wx', 'wy', 'z_x', 'z_y', 'rms_x',
                'rms_y', 'intensity']

        # connect to epics signals and add to data_dict
        self.connect_epics_pvs()

    def update_data(self, wfs_data=None):
        """
        Produce new data from current image
        :return:
        """

        # update timestamps
        self.update_1d_data(self.timestamp_key, self.imager.time_stamp)

        # standalone keys
        standalone_keys = self.image_array_keys + self.image_keys + self.coord_keys

        # standalone wfs keys
        wfs_array_keys = self.wfs_coord_keys + self.wfs_array_keys + self.wfs_image_keys

        # update dictionary
        for key in self.stripchart_imager_keys:
            self.update_1d_data(key, getattr(self.imager, key))

        # update pv's
        for key in self.pv_keys:
            self.update_1d_data(key, self.epics_signals[key].get())

        # get non-stripchart data
        for key in standalone_keys:
            self.data_dict[key] = getattr(self.imager, key)

        # get wfs data
        if wfs_data is not None:
            for key in self.stripchart_wfs_keys:
                self.data_dict[key] = self.update_1d_data(key, wfs_data[key])

            for key in wfs_array_keys:
                self.data_dict[key] = wfs_data[key]

        # update running averages
        for key in self.stripchart_smooth_keys:
            self.running_average(key, key+'_smooth')

    def update_wfs_data(self, wfs_data):
        for key in wfs_data.keys():
            if key in self.image_keys:
                self.data_dict[key] = wfs_data[key]

    def read_pv_names(self):
        # read pv names from the file
        with open(self.filename) as f:
            pv_names = f.readlines()

        # strip the whitespace
        pv_names = [name.strip() for name in pv_names]

        return pv_names

    def update_1d_data(self, dict_key, new_value):
        self.data_dict[dict_key] = np.roll(self.data_dict[dict_key], -1)
        self.data_dict[dict_key][-1] = new_value

    def running_average(self, source_key, dest_key):
        self.data_dict[dest_key] = pd.Series(self.data_dict[source_key]).rolling(10, min_periods=1).mean().values

    def connect_epics_pvs(self):
        # add pv's to data_dict
        for key in self.pv_keys:
            tempSignal = SignalRO(key)
            try:
                tempSignal.wait_for_connection()
                self.epics_signals[key] = tempSignal
                self.data_dict[key] = np.full(self.N, np.nan, dtype=float)
                self.data_dict['key_list'].append(key)
            except TimeoutError:
                print('could not connect to %s' % key)
                self.pv_keys.remove(key)