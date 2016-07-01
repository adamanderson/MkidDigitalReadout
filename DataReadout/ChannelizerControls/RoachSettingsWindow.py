

"""
Author: Alex Walter
Date: May 18, 2016

A class for the settings window for HighTemplar.py. 
"""
from functools import partial
from PyQt4.QtGui import *
from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtCore import Qt
import ConfigParser
from RoachStateMachine import RoachStateMachine


class RoachSettingsWindow(QTabWidget):
    
    resetRoach = QtCore.pyqtSignal(int,int)     #Signal emmited when we change a setting so we can reload it into the ROACH2
    
    def __init__(self,roachNums,config,parent=None):
        """
        Creates settings window GUI
        
        INPUTS:
            roachNums - list of roaches and their numbers
            defaultSettings - ConfigParser object that contains all the default values
            parent - the HighTemplar QMainWindow
        """
        super(RoachSettingsWindow, self).__init__(parent)
        self.setWindowTitle('Settings')
        #self.setTabBar(HorizontalTabWidget())
        #self.setTabBar(FingerTabWidget(parent=self,width=100,height=25))
        self.setUsesScrollButtons(False)
        self._want_to_close = False
        self.roachNums = roachNums
        self.config = config
        
        for roachNum in self.roachNums:
            tab = RoachSettingsTab(roachNum, self.config)
            tab.resetRoach.connect(partial(self.resetRoach.emit,roachNum))
            self.addTab(tab, ''+str(roachNum))
        
        #self.setMovable(True)
        self.setTabsClosable(False)
        #self.resize(self.minimumSizeHint())
        #self.resize(300,1000)
        self.setTabPosition(QTabWidget.West)
        #self.setStyleSheet('QTabBar::tab {color: red;}')
        #self.setStyleSheet('QTabBar::tab {selection-color: red;}')
        
        #self.printColors()
    
    def printColors(self):
        pass
        #for i in range(len(self.roachNums)):
        #    print self.tabBar().tabTextColor(i).name()
    
    def closeEvent(self, event):
        if self._want_to_close:
            self.close()
        else:
            self.hide()
            


class RoachSettingsTab(QMainWindow):
    resetRoach = QtCore.pyqtSignal(int)     #Signal emmited when we change a setting so we can reload it into the ROACH2

    def __init__(self,roachNum,config):
        super(RoachSettingsTab, self).__init__() #parent=None. This is the correct way according to the QTabWidget documentation
        self.roachNum = roachNum
        self.config = config
        
        self.create_main_frame()
    
    def changedSetting(self,settingID,setting):
        """
        When a setting is changed, reflect the change in the config object which is shared across all GUI elements.
        
        INPUTS:
            settingID - the key in the configparser
            setting - the value
        """
        self.config.set('Roach '+str(self.roachNum),settingID,str(setting))
        #If we don't force the setting value to be a string then the configparser has trouble grabbing the value later on for some unknown reason
        
    def create_main_frame(self):
        """
        Makes everything on the tab page
        
        
        """
        self.main_frame = QWidget()
        vbox = QVBoxLayout()
       
        def add2layout(vbox, *args):
            hbox = QHBoxLayout()
            for arg in args:
                hbox.addWidget(arg)
            vbox.addLayout(hbox)
        
        label_roachNum = QLabel('Settings for roach '+str(self.roachNum))
        add2layout(vbox,label_roachNum)
        
        ipAddress = self.config.get('Roach '+str(self.roachNum),'ipAddress')
        self.label_ipAddress = QLabel('ip address: ')
        self.label_ipAddress.setMinimumWidth(110)
        self.textbox_ipAddress = QLineEdit(ipAddress)
        self.textbox_ipAddress.setMinimumWidth(70)
        self.textbox_ipAddress.textChanged.connect(partial(self.changedSetting,'ipAddress'))
        self.textbox_ipAddress.textChanged.connect(lambda x: self.resetRoach.emit(-1))      # reset roach state if ipAddress changes
        add2layout(vbox,self.label_ipAddress,self.textbox_ipAddress)
        

        ddsSyncLag = self.config.getint('Roach '+str(self.roachNum),'ddsSyncLag')
        self.label_ddsSyncLag = QLabel('DDS Sync Lag:')
        self.label_ddsSyncLag.setMinimumWidth(110)
        self.spinbox_ddsSyncLag = QSpinBox()
        self.spinbox_ddsSyncLag.setRange(0,2**10)
        self.spinbox_ddsSyncLag.setValue(ddsSyncLag)
        self.spinbox_ddsSyncLag.valueChanged.connect(partial(self.changedSetting,'ddsSyncLag'))
        self.spinbox_ddsSyncLag.valueChanged.connect(lambda x: self.resetRoach.emit(-1))      # reset roach state if ipAddress changes
        add2layout(vbox,self.label_ddsSyncLag,self.spinbox_ddsSyncLag)
        
        freqFile = self.config.get('Roach '+str(self.roachNum),'freqFile')
        self.label_freqFile = QLabel('Freq file: ')
        self.label_freqFile.setMinimumWidth(110)
        self.textbox_freqFile = QLineEdit(freqFile)
        self.textbox_freqFile.setMinimumWidth(70)
        self.textbox_freqFile.textChanged.connect(partial(self.changedSetting,'freqFile'))
        self.textbox_freqFile.textChanged.connect(lambda x: self.resetRoach.emit(RoachStateMachine.LOADFREQ))
        add2layout(vbox,self.label_freqFile,self.textbox_freqFile)
        
        lofreq = self.config.getfloat('Roach '+str(self.roachNum),'lo_freq')
        lofreq_str = "%.9e" % lofreq
        self.label_lofreq = QLabel('LO Freq [Hz]: ')
        self.label_lofreq.setMinimumWidth(110)
        self.textbox_lofreq = QLineEdit(lofreq_str)
        self.textbox_lofreq.setMinimumWidth(150)
        #self.textbox_lofreq.textChanged.connect(partial(self.changedSetting,'lo_freq'))    # This just saves whatever string you type in
        self.textbox_lofreq.textChanged.connect(lambda x: self.changedSetting('lo_freq',"%.9e" % float(x)))
        self.textbox_lofreq.textChanged.connect(lambda x: self.resetRoach.emit(RoachStateMachine.LOADFREQ))
        add2layout(vbox,self.label_lofreq,self.textbox_lofreq)

        vbox.addStretch()
        
        label_note = QLabel("NOTE: Changing the ip address won't take effect until you re-connect. Likewise, changing the DDS Sync Lag, freq file, or LO Freq requires you to load the freqs/attens again")
        label_note.setWordWrap(True)
        
        vbox.addWidget(label_note)

        self.main_frame.setLayout(vbox)
        self.setCentralWidget(self.main_frame)
        
        





#class HorizontalTabWidget(QtGui.QTabBar):
#    def paintEvent(self, event):
#        for index in range(self.count()):
#            painter = QtGui.QPainter()
#            painter.begin(self)
#            painter.setPen(QtCore.Qt.blue);
#            painter.setFont(QtGui.QFont("Arial", 10));
#            tabRect = self.tabRect(index)
#            painter.drawText(tabRect, QtCore.Qt.AlignVCenter | QtCore.Qt.TextDontClip, self.tabText(index));
#            painter.end()
#    
#    def sizeHint(self):
#        return QtCore.QSize(60, 130)
class FingerTabWidget(QtGui.QTabBar):
    """
    This class should extend QTabBar and overload the paintEvent() so that the tabs are on the left and text is horizontal
    
    I can't get the text color to change though...
    """
    def __init__(self, *args, **kwargs):
        self.tabSize = QtCore.QSize(kwargs.pop('width'), kwargs.pop('height'))
        super(FingerTabWidget, self).__init__(*args, **kwargs)
        self.setStyleSheet('QTabBar::tab {color: red;}')
        self.setStyleSheet('QTabBar::tab {selection-color: red;}')

    def paintEvent(self, event):
        painter = QtGui.QStylePainter(self)
        painter.setPen(Qt.red)
        option = QtGui.QStyleOptionTab()

        #painter.begin(self)
        for index in range(self.count()):
            #print ''+str(index)+str(option.palette.color(QPalette.Text).name())
            
            #print self.tabText(index)
            
            
            self.initStyleOption(option, index)
            self.setTabTextColor(index,Qt.red)
            #print option.palette.text().color().name()
            #print painter.brush().color().name()
            #print ''+str(index)+str(option.palette.color(QPalette.Text).name())
            option.palette.setColor(QPalette.Text, Qt.red)
            #print ''+str(index)+str(option.palette.color(QPalette.Text).name())
            option.palette.setColor(QPalette.HighlightedText, Qt.red)
            option.palette.setColor(QPalette.Foreground, Qt.red)
            option.palette.setColor(QPalette.WindowText, Qt.red)
            tabRect = self.tabRect(index)
            tabRect.moveLeft(10)
            painter.drawControl(QtGui.QStyle.CE_TabBarTabShape, option)
            painter.drawControl(QtGui.QStyle.CE_TabBarTabLabel, option)
            painter.drawText(tabRect, QtCore.Qt.AlignVCenter |\
                             QtCore.Qt.TextDontClip, \
                             self.tabText(index));
            #print tabRect
            #painter.drawText(tabRect,0,self.tabText(index))
            print self.tabTextColor(index).name()
            
        #painter.end()
    def tabSizeHint(self,index):
        return self.tabSize








