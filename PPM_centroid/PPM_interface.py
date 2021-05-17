#!/usr/bin/env python
# coding: utf-8

from datetime import datetime
from epics import PV
import numpy as np
import imageio
import scipy.ndimage.interpolation as interpolate
import sys
import time
import json
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
from PyQt5.uic import loadUiType
from PyQt5.QtCore import Qt
import warnings
from processing_module import RunProcessing
from Image_registration_epics import App
import PPM_widgets
from imager_data import DataHandler
from motion_module import Calibration, Alignment
from io_module import ImagerHdf5, ElogHandler
from subprocess import check_output
import os


local_path = os.path.dirname(os.path.abspath(__file__))


Ui_MainWindow, QMainWindow = loadUiType(local_path+'/PPM_screen.ui')

class PPM_Interface(QtGui.QMainWindow, Ui_MainWindow):
    kill_sig = QtCore.pyqtSignal()
    reset_sig = QtCore.pyqtSignal()
    save_sig = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, args=None):
        super(PPM_Interface, self).__init__()
        self.setupUi(self)

        if args is not None:
            print(args.camera)
            cam = args.camera
        else:
            cam = 'IM1L0'

        self.local_path = os.path.dirname(os.path.abspath(__file__))

        path1 = os.path.dirname(os.path.abspath(__file__))
        path2 = os.path.abspath(os.getcwd())
        print(path1)
        print(path2)

        # button to start calculations
        self.runButton.clicked.connect(self.change_state)
        # button to start calibration
        self.calibrateButton.clicked.connect(self.calibrate)
        self.alignmentButton.clicked.connect(self.align_focus)
        self.actionReset_Plots.triggered.connect(self.reset_plots)
        self.actionSave_Data.triggered.connect(self.save_data)

        self.plotButton.clicked.connect(self.make_new_plot)
        # method to save an image. Maybe replace and/or supplement this with image "recording" in the future
        self.actionSave.triggered.connect(self.save_image)
        # open alignment screen for calculating center and pixel size
        self.actionAlignment_Screen.triggered.connect(self.run_alignment_screen)
        self.actionSave_with_hdf5_plugin.triggered.connect(self.save_hdf5)
        self.actionPost_to_elog.triggered.connect(self.elog_post)
        self.trajectoryButton.clicked.connect(self.capture_trajectory)

        self.unhappyCheckBox.toggled.connect(self.unhappy_trajectory)
        self.happyCheckBox.toggled.connect(self.happy_trajectory)

        # adjustment for amount of time to show on plots (this should be cleaned up later)
        self.plotRangeLineEdit.returnPressed.connect(self.set_time_range)
        self.wfsPlotRangeLineEdit.returnPressed.connect(self.set_time_range)

        # connect line combo box
        self.lineComboBox.currentIndexChanged.connect(self.change_line)
        # connect imager combo box
        self.imagerComboBox.currentIndexChanged.connect(self.change_imager)

        # list of QAction objects for controlling the image orientation
        self.orientation_actions = [self.action0, self.action90, self.action180, self.action270, 
                self.action0_flip, self.action90_flip, self.action180_flip, self.action270_flip]

        self.groupBox_3.setObjectName("CentroidStatsGroupBox")
        self.groupBox_5.setObjectName("WavefrontStatsGroupBox")

        # dictionary of QAction objects. Probably this could replace the above list eventually, but it works so won't
        # break it for now...
        self.orientation_dict = {
                'action0': self.action0,
                'action90': self.action90,
                'action180': self.action180,
                'action270': self.action270,
                'action0_flip': self.action0_flip,
                'action90_flip': self.action90_flip,
                'action180_flip': self.action180_flip,
                'action270_flip': self.action270_flip
                }

        # connect orientation actions
        for action in self.orientation_actions:
            action.triggered.connect(self.change_orientation)

        # connect method to save the current orientation
        self.actionSave_orientation.triggered.connect(self.save_orientation)

        # set orientation
        self.orientation = 'action0'

        # initialize tab to basic tab
        self.tabWidget.setCurrentIndex(0)

        # connect levels to image
        self.imageWidget.connect_levels(self.levelsWidget)
        # connect crosshairs to image
        self.imageWidget.connect_crosshairs(self.crosshairsWidget)

        # connect stats to image. This is for displaying the circle on the image centered on the
        # beam with diameter of 2*FWHM
        self.imagerStats.connect_image(self.imageWidget)

        # wavefront retrieval
        self.wavefrontWidget.change_lineout_label('Phase (rad)')

        # connect levels to wavefront image
        self.wavefrontWidget.connect_levels(self.wavefrontLevelsWidget)
        # connect wavefront image to crosshairs
        self.wavefrontWidget.connect_crosshairs(self.wavefrontCrosshairsWidget)

        # add centroid plot
        self.centroid_plot = PPM_widgets.StripChart(self.centroidCanvas, u'Beam Centroid (\u03BCm)')

        # labels and keys for plots
        labels = ['X', 'Y', 'X smoothed', 'Y smoothed']
        keys = ['x', 'y', 'x_smooth', 'y_smooth']

        # plot for centroids
        self.centroid_plot.addSeries(keys, labels)

        # add FWHM plot
        self.width_plot = PPM_widgets.StripChart(self.fwhmCanvas, u'Beam FWHM (\u03BCm)')
        self.width_plot.addSeries(keys, labels)

        # add focus distance plot
        self.focus_plot = PPM_widgets.StripChart(self.focusCanvas, 'Focus position (mm)')
        self.focus_plot.addSeries(keys, labels)

        # add rms error plot
        self.rms_plot = PPM_widgets.StripChart(self.rmsErrorCanvas, 'RMS wavefront error (rad)')
        self.rms_plot.addSeries(keys, labels)

        # make a list of all the plots
        self.all_plots = [self.centroid_plot, self.width_plot, self.focus_plot, self.rms_plot]

        # get hutch
        try:
            #self.hutch = check_output('get_curr_exp').decode('utf-8').replace('\n','')[:3]
            self.hutch = check_output('hostname').decode('utf-8').replace('\n','')[:3]

        except:
            self.hutch = check_output('hostname').decode('utf-8').replace('\n','')[:3]

        print('hutch: %s' % self.hutch)

        # initialize data handler
        self.data_handler = DataHandler(self.hutch)

        # load in imager information
        with open(self.local_path+'/imager_info.json') as json_file:
            self.imager_info = json.load(json_file)

        # list of beamlines
        self.line_list = [key for key in self.imager_info]

        # dictionary of imagers
        self.imager_dict = {}
        for line in self.line_list:
            self.imager_dict[line] = [key for key in self.imager_info[line]]

        # list of imagers with a wavefront sensor
        #self.WFS_list = ['IM2K0', 'IM2L0', 'IM5K4', 'IM6K4', 'IM6K2', 'IM3K3', 'IM4L1']

        # dictionary of wavefront sensor corresponding to imager
        #self.WFS_dict = {
        #    'IM2K0': 'PF1K0',
        #    'IM2L0': 'PF1L0',
        #    'IM5K4': 'PF1K4',
        #    'IM6K4': 'PF2K4',
        #    'IM6K2': 'PF1K2',
        #    'IM3K3': 'PF1K3',
        #    'IM4L1': 'PF1L1'
        #}

        # initialize line combo box
        self.lineComboBox.addItems(self.line_list)

        self.line = None
        valid_cam = False
        # figure out which line
        for key in self.imager_dict.keys():
            if cam in self.imager_dict[key]:
                self.line = key
                valid_cam = True
        #if self.line is None:
        #    self.line = 'L0'

        line_index = self.line_list.index(self.line)

        # initialize imager list and imager
        #self.imager_list = self.imager_dict['L0']
        self.imager_list = self.imager_dict[self.line]
        if valid_cam:
            self.imager = cam
        #self.imager = self.imager_list[0]
        cam_index = self.imager_list.index(cam)
        print(cam_index)

        # set wavefront sensor attribute
        self.wfs_name = None

        # make sure this initializes properly
        #self.imagerpv_list = self.imagerpv_dict[self.line]
        #self.imagerpv = self.imagerpv_list[cam_index]

        self.curr_imager_dict = self.imager_info[self.line][self.imager]

        self.imagerpv = self.curr_imager_dict['prefix']
        #self.imagerpv = self.imager_info[self.line][self.imager]['prefix']

        self.imagerComboBox.clear()
        self.imagerComboBox.addItems(self.imager_list)
       
        # hdf5 object
        self.imager_h5 = ImagerHdf5(prefix=self.imagerpv, name=self.imager)

        # disable wavefront checkbox by default since IM1L0 doesn't have a WFS
        self.wavefrontCheckBox.setEnabled(False)

        # disable calibrate button unless processing is running
        self.calibrateButton.setEnabled(False)
        self.alignmentButton.setEnabled(False)

        # more initialization...
        self.lineComboBox.setCurrentIndex(line_index)
        self.imagerComboBox.setCurrentIndex(cam_index)

        # try to initialize elog
        self.elog_handler = ElogHandler()

        # initialize registration object
        self.processing = None
        self.calib = None
        self.alignment_message = None
        self.align = None
        self.alignment_thread = None

        self.plots = []

        # attribute describing if trajectory is set
        self.trajectory_is_set = False

    def calibrate(self):
        calib_plot = PPM_widgets.NewPlot(self, self.data_handler.plot_keys())
        calib_plot.xaxis_comboBox.setCurrentText('timestamps')
        calib_plot.yaxis_comboBox.setCurrentText('MR2K4:KBO:MMS:PITCH.RBV')
        calib_plot.min_lineEdit.setText('-100')
        calib_plot.update_min()
        calib_plot.update_axes()
        calib_plot.show()
        self.plots.append(calib_plot)

        self.calibrateButton.setEnabled(False)

        self.calib = Calibration(self.data_handler)
        #self.calib.finished.connect(lambda event=0: calib_plot.closeEvent(event))
        #self.calib.finished.connect(calib_plot.close)
        self.calib.finished.connect(self.enable_calibrate)
        self.calib.start()

    def enable_calibrate(self):
        self.calibrateButton.setEnabled(True)

    def unhappy_trajectory(self, checked):
        if checked:
            self.happyCheckBox.setChecked(False)
            self.trajectoryButton.setEnabled(True)
            self.trajectory_is_set = False
        else:
            if not self.happyCheckBox.isChecked():
                self.trajectoryButton.setEnabled(False)

    def happy_trajectory(self, checked):
        if checked:
            self.unhappyCheckBox.setChecked(False)
            self.trajectoryButton.setEnabled(True)
            self.trajectory_is_set = True
        else:
            if not self.unhappyCheckBox.isChecked():
                self.trajectoryButton.setEnabled(False)

    def align_focus(self):

        # get current z position goals
        try:
            z_x_target = float(self.xFocusLineEdit.text())
        except ValueError:
            z_x_target = 0.0
            self.xFocusLineEdit.setText('0.0')
        try:
            z_y_target = float(self.yFocusLineEdit.text())
        except ValueError:
            z_y_target = 0.0
            self.yFocusLineEdit.setText('0.0')

        # disable alignment button
        self.alignmentButton.setEnabled(False)

        goals = {
            'x': np.array([z_x_target, 0]),
            'y': np.array([z_y_target, 0])
        }

        self.alignment_message = QtWidgets.QMessageBox()
        self.align = Alignment(self.data_handler, self.curr_imager_dict, goals)
        self.align.sig_finished.connect(self.alignment_finished)

        # initialize a new thread
        self.alignment_thread = QtCore.QThread()

        self.alignment_thread.finished.connect(self.enable_align)
        # move to new thread and connect to thread signals
        self.align.moveToThread(self.alignment_thread)
        self.alignment_thread.started.connect(self.align.run)
        self.alignment_thread.finished.connect(self.align.cancel)

        # make a dialog box to allow killing the thread
        self.alignment_message.setIcon(QtWidgets.QMessageBox.Information)
        self.alignment_message.setText("Attempting focus alignment")
        self.alignment_message.setWindowTitle("Alignment")
        self.alignment_message.setStandardButtons(QtWidgets.QMessageBox.Cancel)

        #self.alignment_message.buttonClicked.connect(self.kill_sig.emit)
        #self.alignment_message.buttonClicked.connect(self.align.cancel)
        #self.alignment_message.buttonClicked.connect(self.enable_align)
        self.alignment_message.buttonClicked.connect(self.alignment_canceled)

        self.alignment_thread.finished.connect(self.alignment_message.close)
        # start alignment
        self.alignment_thread.start()

        self.alignment_message.exec()

    def alignment_finished(self):
        self.alignment_thread.quit()
        self.alignment_thread.wait()
        try:
            self.alignment_message.close()
        except:
            print('message already closed')
        self.enable_align()

    def alignment_canceled(self):
        if self.alignment_thread is not None:
            self.alignment_thread.quit()
            self.alignment_thread.wait()
            self.enable_align()

    def enable_align(self):
        #if self.wfs_name=='PF1K4':
        try:
            if 'hutch' in self.curr_imager_dict.keys():
                allowed_hutch = self.hutch.lower()==self.curr_imager_dict['hutch']
            else:
                allowed_hutch = False
            wfs_exists = self.wfs_name is not None
            wfs_calc = self.wavefrontCheckBox.isChecked()
            if allowed_hutch and wfs_exists and wfs_calc:
                self.alignmentButton.setEnabled(True)
        except:
            print('image_info.json file is incomplete')

    def make_new_plot(self):
        plot_window = PPM_widgets.NewPlot(self, self.data_handler.plot_keys())
        plot_window.show()
        self.plots.append(plot_window)

    def uncheck_all(self):
        """
        Method to uncheck all orientation options.
        """
        for action in self.orientation_actions:
            action.setChecked(False)

    def change_orientation(self):
        """
        Method that is called when an orientation menu item is selected. This causes a change to the orientation
        of the displayed image.
        """
        menu_item = self.sender()

        self.uncheck_all()
        menu_item.setChecked(True)

        self.orientation = menu_item.objectName()

        # check if running, if so send orientation information
        if self.processing is not None:
            self.processing.set_orientation(self.orientation)

    def load_orientation(self):
        """
        Method to load the previously saved orientation. Defaults to no rotation if there hasn't been anything saved.
        """
        try:
            # read the imagers.db file
            with open('/cds/home/s/seaberg/Commissioning_Tools/PPM_centroid/imagers.db') as json_file:
                data = json.load(json_file)
            # set orientation from the file
            self.orientation = data[self.imager]['orientation']
            print('using orientation %s' % self.orientation)
        except json.decoder.JSONDecodeError:
            # catch the exception that the file doesn't exist
            self.orientation = 'action0'
        except KeyError:
            # catch the exception that the orientation hasn't been saved for this imager
            print('orientation not set, using 0.')
            self.orientation = 'action0'

        # set appropriate checkbox and uncheck any other boxes
        self.uncheck_all()
        self.orientation_dict[self.orientation].setChecked(True)

    def save_orientation(self):
        """
        Method to save the current image orientation.
        """
        # get current file contents
        try:
            with open('imagers.db') as json_file:
                data = json.load(json_file)

        except json.decoder.JSONDecodeError:
            # give up if there's no file for now...
            pass

        # check if there is already information about this imager
        if self.imager in data:
            # if so, add orientation information
            data[self.imager]['orientation'] = self.orientation
        else:
            # if not, initialize information about this imager
            data[self.imager] = {}
            data[self.imager]['orientation'] = self.orientation

        # write to the file under the corresponding imager field
        with open('imagers.db', 'w') as outfile:
            json.dump(data, outfile, indent=4)

    def capture_trajectory(self):
        basename = self.get_basename()

        # save images
        image_name = self.save_hdf5(basename=basename)
        # save data

        if self.hutch=='lfe':
            home_path = '/cds/home/opr/xppopr'
        elif self.hutch=='kfe':
            home_path = '/cds/home/opr/tmoopr'
        else:
            home_path = check_output('cd ~; pwd',shell=True).decode('utf-8').replace('\n','')

        data_path = home_path+'/trajectory/data/'
        data_name = data_path+self.imager+'_'+basename + '_data.h5'
        self.save_sig.emit(data_name)
       
        # post to elog
        self.elog_handler.post_trajectory(self.trajectory_is_set, self.imager, 
                self.imagerControls, self.imagerStats, self.photonEnergyLabel, 
                image_name, data_name)

    def elog_post(self):
        self.elog_handler.post_stats(self.imager, self.imagerControls, self.imagerStats,
            self.photonEnergyLabel)

    def get_basename(self):
        # get state
        state = self.imagerControls.yStateReadback.text()

        # get pointing information
        if self.trajectory_is_set:
            pointing = 'pointed'
        else:
            pointing = 'unpointed'
        
        # get timestamp
        timestamp = datetime.now()
        date_str = str(timestamp.date())
        time_str = timestamp.time().isoformat(timespec='seconds')
        time_string = '%s_%s' % (date_str, time_str)
        #basename = '%s_trajectory_%s' % (self.imager, time_string)
        basename = '%s_%s_%s' % (state, time_string, pointing)
        
        return basename

    def save_hdf5(self, basename=None):
        if basename is None:
            basename = self.get_basename()
        self.imager_h5.prepare(baseName=basename+'_images', nImages=10)
        self.imager_h5.write()
        path = self.imager_h5.imagerh5.file_path.get()
        name = self.imager_h5.imagerh5.file_name.get()
        full_name = path+name+'_1.h5'
        return full_name


    def set_time_range(self, time_range=10.0):
        """
        Method to set the time range of the centroid, etc plots.
        :param time_range: float
            time for x-axis in seconds
        """
        # check if this is called as a callback
        if self.sender():
            rangeLineEdit = self.sender()
            try:
                time_range = float(rangeLineEdit.text())
            except ValueError:
                time_range = 10.0
                rangeLineEdit.setText('10.0')

        # set time range for all stripchart-type plots
        for plot in self.all_plots:
            plot.set_time_range(time_range)

    def setup_legend(self, legend):
        """
        Method to set up a legend for a plot. This should probably belong in the PPM_widgets module.
        Parameters
        ----------
        legend: string
            pyqtgraph Legend object
        """

        # set style: white text, 10pt
        legendLabelStyle = {'color': '#FFF', 'size': '10pt'}
        # the following was just taken from the web...
        for item in legend.items:
           for single_item in item:
               if isinstance(single_item, pg.graphicsItems.LabelItem.LabelItem):
                   single_item.setText(single_item.text, **legendLabelStyle)

    def run_alignment_screen(self):
        """
        Method to open the alignment screen
        """

        cam_name = self.imagerpv

        alignment_app = App(parent=self, imager=cam_name)
        alignment_app.show()

    def change_line(self, index):
        """
        Method to change which beamline from which to select an imager.

        Parameters
        ----------
        index: int
            index corresponding to which beamline as defined in self.line_list
        """
        # update line
        self.line = self.line_list[index]
        self.imager_list = self.imager_dict[self.line]
        #self.imagerpv_list = self.imagerpv_dict[self.line]
        self.imagerComboBox.clear()
        self.imagerComboBox.addItems(self.imager_list)
        self.change_imager(0)

        if 'L' in self.line:
            self.photonEnergyLabel.channel = 'ca://PMPS:LFE:PE:UND:CurrentPhotonEnergy_RBV'
        else:
            self.photonEnergyLabel.channel = 'ca://PMPS:KFE:PE:UND:CurrentPhotonEnergy_RBV' 

    def change_imager(self, index):
        """
        Method to change settings based on selection of a new imager

        Parameters
        ----------
        index: int
            index corresponding to which imager as defined in self.imager_list
        """
        # update imager
        self.imager = self.imager_list[index]
        self.imageGroupBox.setTitle(self.imager)
        self.wavefrontGroupBox.setTitle(self.imager)
        self.curr_imager_dict = self.imager_info[self.line][self.imager]
        # check if this imager has a wavefront sensor
        #if self.imager in self.WFS_list:
        if 'wfs' in self.curr_imager_dict.keys():
            self.wavefrontCheckBox.setEnabled(True)
            # update wfs_name
            #self.wfs_name = self.WFS_dict[self.imager]
            self.wfs_name = self.curr_imager_dict['wfs']
        else:
            self.wavefrontCheckBox.setChecked(False)
            self.wavefrontCheckBox.setEnabled(False)
            # no wavefront sensor associated with this imager
            self.wfs_name = None

        #self.imagerpv = self.imagerpv_list[index]
        self.imagerpv = self.curr_imager_dict['prefix']
        self.imagerControls.change_imager(self.imagerpv)

        # hdf5 object
        self.imager_h5 = ImagerHdf5(prefix=self.imagerpv, name=self.imager)

        self.wfsControls.change_wfs(self.wfs_name)
        # uninitialize data handler
        self.data_handler.uninitialize()
        self.load_orientation()

    def enable_run_button(self):
        self.runButton.setEnabled(True)
        self.statusbar.clearMessage()
        if self.runButton.text() == 'Stop':
            #self.alignmentButton.setEnabled(True)
            self.enable_align()

    def quit_thread(self):
        self.thread.quit()

    def reset_plots(self):
        self.reset_sig.emit()

    def change_state(self):
        """
        Method to start the calculation running, or stop it.
        """

        # check if "Run" was selected
        if self.runButton.text() == 'Run':

            self.runButton.setEnabled(False)

            # check if we are going to calculate the wavefront. Set wfs_name to None if not.
            if self.wavefrontCheckBox.isChecked():
                wfs_name = self.wfs_name
            else:
                wfs_name = None

            # get Talbot fraction. This will eventually be automated based on the photon energy and WFS state.
            try:
                fraction = float(self.wfsControls.fractionLineEdit.text())
            except ValueError:
                fraction = 1
            
            # initialize a new thread
            self.thread = QtCore.QThread()

            # initialize processing object. This really needs a dictionary as input...
            self.processing = RunProcessing(self.imagerpv, self.data_handler, self.averageWidget, wfs_name=wfs_name,
                                            threshold=self.imagerStats.get_threshold(), focusFOV=self.displayWidget.FOV, fraction=fraction, focus_z=self.displayWidget.focus_z, displayWidget=self.displayWidget, thread=self.thread, hutch=self.hutch)

            # connect processing object to plotting function
            self.processing.sig.connect(self.update_plots)
            
            # connect to initialized signal
            self.processing.sig_initialized.connect(self.enable_run_button)

            # find out what the FOV of the screen is
            width, height = self.processing.get_FOV()
            # set the orientation for processing
            self.processing.set_orientation(self.orientation)

            # update viewboxes based on FOV
            self.imageWidget.update_viewbox(width, height)
            if self.displayWidget.display_choice == 'Focus':
                self.wavefrontWidget.update_viewbox(self.displayWidget.FOV, self.displayWidget.FOV)
            else:
                # this would eventually change for the FFT option
                self.wavefrontWidget.update_viewbox(width, height)

            # update crosshair sizes
            self.crosshairsWidget.update_crosshair_width()
            self.wavefrontCrosshairsWidget.update_crosshair_width()

            # update width for circle displayed on beam
            self.imagerStats.update_width()

            # initialize a new thread
            self.thread = QtCore.QThread()

            # move to new thread and connect to thread signals
            self.processing.moveToThread(self.thread)
            self.thread.started.connect(self.processing.run)
            self.thread.finished.connect(self.enable_run_button)
            self.kill_sig.connect(self.processing.stop)
            self.reset_sig.connect(self.processing.reset_plots)
            self.processing.sig_finished.connect(self.quit_thread)
            self.save_sig.connect(self.processing.save_data)

            # start processing
            self.thread.start()

            # change the button state
            self.runButton.setText('Stop')
            #self.runButton.setEnabled(True)
            # disable wavefront sensor checkbox until stop is pressed
            self.wavefrontCheckBox.setEnabled(False)

            # disable imager selection until Stop is pressed
            self.lineComboBox.setEnabled(False)
            self.imagerComboBox.setEnabled(False)
            #self.calibrateButton.setEnabled(True)
            #self.alignmentButton.setEnabled(True)
            self.statusbar.showMessage('Starting acquisition...')

        # check if "Stop" was selected
        elif self.runButton.text() == 'Stop':

            self.runButton.setEnabled(False)
            # stop processing and quit the thread
            #self.thread.quit()
            #self.thread.wait()
            self.kill_sig.emit()
            self.statusbar.showMessage('Stopping acquisition...')

            # update the button to be ready to "Run"
            self.runButton.setText('Run')
            self.calibrateButton.setEnabled(False)
            self.alignmentButton.setEnabled(False)
            # re-enable wavefront sensor checkbox if imager is has a wavefront sensor
            #if self.imager in self.WFS_list:
            if 'wfs' in self.curr_imager_dict.keys():

                self.wavefrontCheckBox.setEnabled(True)

            #self.runButton.setEnabled(True)
            # re-enable imager selection
            self.lineComboBox.setEnabled(True)
            self.imagerComboBox.setEnabled(True)

    @staticmethod
    def normalize_image(image):
        """
        This probably belongs somewhere else... The idea is to normalize an image to 8-bit dynamic range
        for saving to a png file

        Parameters
        ----------
        image: ndarray (N,M)
            input image
        Returns
        -------
        ndarray (N,M)
            output image
        """
        image -= np.min(image)
        image *= 255./float(np.max(image))
        image = np.array(image,dtype='uint8')
        return image

    def save_data(self):
        """
        Method to get a filename for saving data, and send a signal
        to save the data
        """
        formats = 'HDF5 file (*.h5)'
        filename = QtGui.QFileDialog.getSaveFileName(self,
                'Save Data', 'untitled.h5', formats)

        if not filename[0] == '':
            filename = PPM_Interface.get_filename(filename, fmt='.h5')
            self.save_sig.emit(filename)

    def save_image(self):
        """
        Method to save a png image based on the latest image grabbed
        """
        formats = 'Portable Network Graphic (*.png)'
        filename = QtGui.QFileDialog.getSaveFileName(self, 
                'Save Image','untitled.png',formats)
        # make sure a file name was chosen
        if not filename[0] == '':
            # normalize the image and write to file
            im = App.normalize_image(self.data_handler.data_dict['profile'])
            filename = PPM_Interface.get_filename(filename, fmt='.png')
            imageio.imwrite(filename,im)
        print(filename)

    @staticmethod
    def get_filename(name, fmt='png'):
        """
        Method to get the filename from QFileDialog
        Parameters
        ----------
        name: list of strings
            first entry is the full path including file name, second entry is the extension

        Returns
        -------
        string
            full path including file name and extension
        """
        path = name[0]
        extension = name[1].split('*')[1][0:len(fmt)]
        if path[-len(fmt):] != extension:
            path = path + extension
        return path

    def closeEvent(self, event):
        """
        Method to control what happens if the window is closed.

        Parameters
        ----------
        event: signal
        """
        # check if anything is running, otherwise do nothing else
        if self.runButton.text() == 'Stop':
            self.processing.stop()
            self.thread.quit()
            self.thread.wait()

    def update_plots(self):
        """
        Method to update all the plots. Would be nice to find a way to make this less explicit. One idea would be
        to pass the dictionary keys into the plots when they are first initialized. Seems like passing the dictionary
        around to all the plot functions probably only passes by reference or something.

        Parameters
        ----------
        data_dict: dict
            This is where all the data to display is stored
        """

        data_dict = self.data_handler.data_dict

        # get validity
        centroid_validity = data_dict['centroid_is_valid']
        wavefront_validity = data_dict['wavefront_is_valid']

        # check if the most recent measurement was valid
        if centroid_validity[-1]:
            self.groupBox_3.setStyleSheet("QGroupBox#CentroidStatsGroupBox { border: 2px solid green;}")
        else:
            self.groupBox_3.setStyleSheet("QGroupBox#CentroidStatsGroupBox { border: 2px solid red;}")

        # check if the most recent measurement was valid
        if wavefront_validity[-1]:
            self.groupBox_5.setStyleSheet("QGroupBox#WavefrontStatsGroupBox { border: 2px solid green;}")
        else:
            self.groupBox_5.setStyleSheet("QGroupBox#WavefrontStatsGroupBox { border: 2px solid red;}")

        x = data_dict['x']
        y = data_dict['y']
        image_data = data_dict['profile']
        xlineout = data_dict['lineout_x']
        ylineout = data_dict['lineout_y']
        xprojection = data_dict['projection_x']
        yprojection = data_dict['projection_y']
        fit_x = data_dict['fit_x']
        fit_y = data_dict['fit_y']

        # wfs widget plots
        x_prime = data_dict['x_prime']
        y_prime = data_dict['y_prime']
        x_res = data_dict['x_res']
        y_res = data_dict['y_res']
        x_res_fit = np.zeros_like(x_res)
        y_res_fit = np.zeros_like(y_res)

        # update main image and lineouts
        self.imageWidget.update_plots(image_data, x, y, xprojection, yprojection, fit_x, fit_y, 
                xlineout_data=xlineout, ylineout_data=ylineout)

        # update wavefront tab
        if self.wavefrontCheckBox.isChecked():

            # get focus coordinates
            xf = data_dict['xf']

            # check what is supposed to be displayed. Would be nice to also clean this up
            if self.displayWidget.display_choice == 'Focus':
                xline = data_dict['focus_horizontal']
                yline = data_dict['focus_vertical']
                self.wavefrontWidget.update_plots(data_dict['focus'], xf, xf, xline, yline, xline, yline)
            elif self.displayWidget.display_choice == 'Fourier transform':
                self.wavefrontWidget.update_plots(data_dict['F0'], x, y, xprojection, yprojection, fit_x, fit_y)
            elif self.displayWidget.display_choice == 'Phase':
                self.wavefrontWidget.update_plots(data_dict['wave'], x_prime, y_prime, x_res, y_res, x_res, y_res)

            # update wavefront tab stripchart plots
            self.focus_plot.update_plots(data_dict['timestamps'], x=data_dict['z_x'], y=data_dict['z_y'], x_smooth=data_dict['z_x_smooth'], y_smooth=data_dict['z_y_smooth'])
            self.rms_plot.update_plots(data_dict['timestamps'], x=data_dict['coma_x'], y=data_dict['coma_y'], x_smooth=data_dict['rms_x_smooth'], y_smooth=data_dict['rms_y_smooth'])

            self.wfsStats.update_stats(data_dict)

        # update centroid plots
        self.centroid_plot.update_plots(data_dict['timestamps'], x=data_dict['cx'], y=data_dict['cy'], x_smooth=data_dict['cx_smooth'], y_smooth=data_dict['cy_smooth'])
        self.width_plot.update_plots(data_dict['timestamps'], x=data_dict['wx'], y=data_dict['wy'], x_smooth=data_dict['wx_smooth'], y_smooth=data_dict['wy_smooth'])

        self.label.setText(data_dict['tx'])

        # update stats values
        self.imagerStats.update_stats(data_dict)

        for plot in self.plots:
            plot.update_plot(data_dict, self.data_handler.plot_keys())
