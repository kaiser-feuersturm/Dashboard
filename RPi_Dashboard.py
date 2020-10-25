import psutil
from datetime import datetime, timedelta
import time
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import cartopy.crs as ccrs
from cartopy.feature.nightshade import Nightshade

cpuTimes = psutil.cpu_times()
cpuCount = psutil.cpu_count()

sysStatsLogLengthInSecs = 60


def updateSysStats(sysStats):
    localTime = datetime.now()
    cpuPercent = psutil.cpu_percent(interval=1, percpu=True)
    memStats = psutil.virtual_memory()
    tmpSensors = psutil.sensors_temperatures()
    sysStats[localTime] = {
        'cpuPercent': cpuPercent,
        'memPercent': memStats.percent,
        'cpuTempCel': tmpSensors['cpu-thermal'][0].current,
    }
    sysStats = {k:v for (k,v) in sysStats.items() if (localTime-k).total_seconds()<sysStatsLogLengthInSecs}
    return sysStats
    

def extractSysStats(sysStats, cpnt='cpuPercent'):
    if 'time'==cpnt:
        timestamps = list(sysStats.keys())
        lastLogTime = max(timestamps)
        retVal = [(kt-lastLogTime).total_seconds() for kt in timestamps]
    else:
        retVal = [v[cpnt] for v in list(sysStats.values())]
        if 'cpuPercent'==cpnt:
            retVal = np.transpose(retVal)
    
    return retVal


class updateAxes:
    def __init__(self, fig):
        self.sysStats = {}
        self.fig = fig
        plt.subplots_adjust(wspace=.3)
        self.ax1 = fig.add_subplot(221, projection='3d', xlim=(-sysStatsLogLengthInSecs, 0), zlim=(0, 100), xlabel='time (s)', ylabel='CPU#', zlabel='CPU%')
        self.ax1.set_zlabel('CPU%', rotation='vertical')
        self.ax1props = {'xlim':(-sysStatsLogLengthInSecs, 0), 'zlim':(0, 100), 'xlabel':'time (s)', 'ylabel':'CPU#', 'zlabel':'CPU%'}
        self.ax2 = fig.add_subplot(222, xlim=(-sysStatsLogLengthInSecs, 0), ylim=(0, 100), xlabel='time (s)', ylabel='T$_{CPU}$ ($^o$C)')
        self.ax3 = fig.add_subplot(223, xlim=(-sysStatsLogLengthInSecs, 0), ylim=(0, 100), xlabel='time (s)', ylabel='mem%')
        for axItr in [self.ax2, self.ax3]:
            axItr.grid(True, alpha=.5)
            axItr.yaxis.set_label_position('right')
            axItr.yaxis.tick_right()
#         self.ax4 = fig.add_subplot(224, projection=ccrs.NearsidePerspective(central_longitude=-74, central_latitude=40.5))
        self.ax4 = fig.add_subplot(224, projection=ccrs.Robinson())
        self.ax4TimeToUpdate = datetime.now()
        # initialize
        self.sysStats = updateSysStats(self.sysStats)
        self.lines = [[] for idx in range(4)]
        sysStatsX = extractSysStats(self.sysStats, 'time')
        #CPU percentage
        cpuPercent = extractSysStats(self.sysStats, 'cpuPercent')
        #CPU temperature
        cpuTempCel = extractSysStats(self.sysStats, 'cpuTempCel')
        line, = self.ax2.plot(sysStatsX, cpuTempCel, 'd-r', ms=2)
        self.lines[1].append(line)
        #memory percertange
        memPercent = extractSysStats(self.sysStats, 'memPercent')
        line, = self.ax3.plot(sysStatsX, memPercent, 'o-c', ms=2)
        self.lines[2] = [line]
        #globe
#         self.ax4.stock_img()
        
        
    def __call__(self, i):
        self.sysStats = updateSysStats(self.sysStats)
        sysStatsX = extractSysStats(self.sysStats, 'time')
        #CPU percentage
        self.ax1.cla()
        self.ax1.update(self.ax1props)
        cpuPercent = extractSysStats(self.sysStats, 'cpuPercent')
        cpuColors = ['y', 'b', 'g', 'm']
        for idx, color in zip(range(4), cpuColors):
            self.ax1.bar(sysStatsX, cpuPercent[idx], width=2, zs=idx, zdir='y', color=color*len(sysStatsX), alpha=.8)
        #CPU temperature
        cpuTempCel = extractSysStats(self.sysStats, 'cpuTempCel')
        self.lines[1][0].set_data(sysStatsX, cpuTempCel)
        #memory percertange
        memPercent = extractSysStats(self.sysStats, 'memPercent')
        self.lines[2][0].set_data(sysStatsX, memPercent)
        #globe
        if max(self.sysStats.keys())>self.ax4TimeToUpdate:
            self.ax4.cla()
            self.ax4.stock_img()
            self.ax4.add_feature(Nightshade(datetime.now(), alpha=.3))
            self.ax4TimeToUpdate += timedelta(seconds=21)
        

fig = plt.figure(figsize=(8, 6), facecolor='w')
animate = updateAxes(fig)
anim = animation.FuncAnimation(fig, animate, interval=1000, repeat=False)
plt.show()