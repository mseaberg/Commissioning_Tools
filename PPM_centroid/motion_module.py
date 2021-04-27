import numpy as np
import time
from pyqtgraph.Qt import QtCore
from ophyd import EpicsSignalRO as SignalRO
from ophyd import EpicsSignal as Signal
from pcdsdevices.mirror import KBOMirror


base_path = '/cds/home/s/seaberg/dev/Commissioning_Tools/PPM_centroid/calibration/'


class Calibration(QtCore.QThread):

    def __init__(self, data_handler):
        #super(Calibration, self).__init__()
        QtCore.QThread.__init__(self)
        self.data_handler = data_handler
        self.mr2k4 = KBOMirror('MR2K4:KBO', name='mr2k4')
        self.mr3k4 = KBOMirror('MR3K4:KBO', name='mr3k4')
        try:
            self.mr2k4.wait_for_connection()
        except:
            print('failed to connect to all mr2k4 signals')
        try:
            self.mr3k4.wait_for_connection()
        except:
            print('failed to connect to all mr3k4 signals')

    def run(self):
        starting_point = self.mr2k4.pitch.position

        for i in range(10):
            self.mr2k4.pitch.mvr(1, wait=True)
            time.sleep(2)
        self.mr2k4.pitch.mv(starting_point)
        print('calibration complete')
        self.quit()


class Alignment(QtCore.QObject):

    sig_finished = QtCore.pyqtSignal()

    def __init__(self, data_handler, curr_imager_dict, goals, curr_hutch):
        super(Alignment, self).__init__()

        photon_energy = SignalRO('PMPS:KFE:PE:UND:CurrentPhotonEnergy_RBV').get()

        hfm_pv = curr_imager_dict['hfm']
        vfm_pv = curr_imager_dict['vfm']

        filename = '{}_{}.npz'.format(curr_imager_dict['hutch'], curr_imager_dict['IP'])

        calib_data = np.load(base_path+filename)
        self.Ax = calib_data['Ax']
        self.Ay = calib_data['Ay']

        self.data_handler = data_handler
        self.hfm = KBMirror(hfm_pv, name=hfm_pv[:5].lower())
        self.vfm = KBMirror(vfm_pv, name=vfm_pv[:5].lower())

        self.lambda0 = 1239.8/photon_energy*1e-9

        # goals is just a dictionary. Each entry in the dictionary is a 1D array. The second entry will probably
        # always be zero since this corresponds to undesirable 3rd order
        self.x_goals = goals['x']
        self.y_goals = goals['y']

    def run(self):

        self.running = True
        self._update()

    def _update(self):
        # need to get some updates from the RunProcessing object to see where we are currently. We also need to

        # need a while loop here to collect some data

        if self.running:

            data_dict = self.data_handler.data_dict
            # wait for at least 3 shots in a row of the incoming data to be valid
            try:
                counter = np.sum(data_dict['wavefront_is_valid'][-3:])
                print('counter %d' % counter)
            except:
                counter = -1
            z_x = np.mean(data_dict['z_x'][-3:])
            z_y = np.mean(data_dict['z_y'][-3:])
            coma_x = np.mean(data_dict['coma_x'][-3:])*self.lambda0
            coma_y = np.mean(data_dict['coma_y'][-3:])*self.lambda0

            if counter < 3:
                QtCore.QTimer.singleShot(2000, self._update)
            else:
                # calculate desired move
                current_x = np.array([z_x, coma_x])
                current_y = np.array([z_y, coma_y])

                delta_x = self.x_goals - current_x
                delta_y = self.y_goals - current_y

                motion_x = np.dot(self.Ax, delta_x)
                motion_y = np.dot(self.Ay, delta_y)

                # move the mirrors
                self.hfm.bender_us.mvr(motion_x[0])
                self.hfm.bender_ds.mvr(motion_x[1])
                self.vfm.bender_us.mvr(motion_y[0])
                self.vfm.bender_ds.mvr(motion_y[1])
                self.sig_finished.emit()

    def cancel(self):
        self.running = False


class Motor():
    def __init__(self, pv_name):
        self.setpoint = Signal(pv_name)
        self.rbv = SignalRO(pv_name+'.RBV', auto_monitor=True)

    def mv(self, target, wait=False, tol=0.1):
        self.set(target)
        if wait:
            while np.abs(self.get() - target) > tol:
                time.sleep(0.2)

    def mvr(self, adjustment, wait=False, tol=0.1):
        target = self.get() + adjustment
        self.mv(target, wait=wait, tol=tol)

    def get(self):
        return self.rbv.value

    def set(self, target):
        self.setpoint.set(target)



class KBMirror():

    def __init__(self, mirror_base, name=None):
        # initialize attributes
        self.name = name
        self.mirror_base = mirror_base
        self.motor_base = self.mirror_base + ':MMS'
        # initialize epics signals
        self.pitch = Motor(self.motor_base+':PITCH')
        self.x = Motor(self.motor_base+':X')
        self.y = Motor(self.motor_base+':Y')
        self.bender_us = Motor(self.motor_base+':BEND:US')
        self.bender_ds = Motor(self.motor_base+':BEND:DS')

