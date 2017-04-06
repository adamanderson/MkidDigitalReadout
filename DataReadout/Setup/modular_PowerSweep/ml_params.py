import os

# data files
mdd = os.environ['MKID_DATA_DIR']
mldir = './Hal_fullres'
trainDir = '../PowerSweep/mlTrainingData'
trainFile = 'ps_train.pkl'
trainBinFile = 'ps_bin_train.pkl'
rawTrainFiles = ['20161016/ps_r7_100mK_a_20161016-155917.h5',
'20160712/ps_r115_FL1_1_20160712-225809.h5',
'20161016_fake/ps_r7_100mK_a_20161016-155917.h5']
#     '20161016/ps_r7_100mK_a_2016101training_s6-155917.h5',
# '20160712/ps_r115_FL1_1_20160712-225809.h5']


# training parameters
res_per_class = 50
level_train = True
trainReps = 200
batches = 50
testFrac = 0.1
max_learning_rate = 0.005
min_learning_rate = 0.0005#0.0001
decay_speed = 200

# neural network hyperparameters
max_nClass = 15
fully_connected = False
recursive = False

# script actions
do_bin_class = False
do_power_class = True

# debug
plot_missed = False
res_per_win = 4
plot_confusion = False
plot_activations = ''
plot_weights = ''

# plot_accuracy =True



