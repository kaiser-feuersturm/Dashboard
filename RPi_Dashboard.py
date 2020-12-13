import sys
import psutil
from datetime import datetime, timedelta
import time
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patheffects as PathEffects
import matplotlib.ticker as ticker
import cartopy.crs as ccrs
from cartopy.feature.nightshade import Nightshade
import json
import urllib3
from suntime import Sun
import math

cpuTimes = psutil.cpu_times()
cpuCount = psutil.cpu_count()

sysStatsLogLengthInSecs = 60
CitiesCoords = {
    'New York': [40.783, -73.967],
    'Hefei': [31.821, 117.227],
    'Las Vegas': [36.175, -115.136],
#     'Troy': [42.732, -73.693],
    'Lahaina': [20.886, -156.675],
}


def updateSysStats(sysStats):
    localTime = datetime.now()
    cpuPercent = psutil.cpu_percent(interval=1, percpu=True)
    memStats = psutil.virtual_memory()
    tmpSensors = psutil.sensors_temperatures()
    sysStats[localTime] = {
        'cpuPercent': cpuPercent,
        'memPercent': memStats.percent,
        'cpuTempCel': tmpSensors['cpu_thermal'][0].current,
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
        argv = [ str(x).lower() for x in sys.argv ]
        darkmode = 'dark' in argv
        self.sysStats = {}
        self.fig = fig
        fig.set_facecolor('k' if darkmode else 'w')
        plt.subplots_adjust(wspace=.3)
        self.ax1 = fig.add_subplot(221, projection='3d', xlim=(-sysStatsLogLengthInSecs, 0), zlim=(0, 100), xlabel='time (s)', ylabel='CPU#', zlabel='CPU%')
        self.ax1.set_zlabel('CPU%', rotation='vertical')
        self.ax1.xaxis.label.set_color('w' if darkmode else 'k')
        self.ax1.yaxis.label.set_color('w' if darkmode else 'k')
        self.ax1.zaxis.label.set_color('w' if darkmode else 'k')
        self.ax1.tick_params(axis='x', colors='w' if darkmode else 'k')
        self.ax1.tick_params(axis='y', colors='w' if darkmode else 'k')
        self.ax1.tick_params(axis='z', colors='w' if darkmode else 'k')
        self.ax1props = {
            'xlim':(-sysStatsLogLengthInSecs, 0),
            'zlim':(0, 100),
            'xlabel':'time (s)',
            'ylabel':'CPU#',
            'zlabel':'CPU%',
            'yticks':np.linspace(0, cpuCount-1, cpuCount),
            'fc':'k' if darkmode else 'w',
        }
        self.ax2 = fig.add_subplot(222, xlim=(-sysStatsLogLengthInSecs, 0), ylim=(0, 100), xlabel='time (s)', ylabel='T$_{CPU}$ ($^o$C)',
                                   fc='k' if darkmode else 'w')
        self.ax2.xaxis.label.set_color('w' if darkmode else 'k')
        self.ax2.tick_params(axis='x', colors='w' if darkmode else 'k')
        self.ax2.yaxis.label.set_color('r')
        self.ax2.tick_params(axis='y', colors='r')
        self.ax3 = self.ax2.twinx()
        self.ax3.set(ylim=(0, 100), ylabel='mem%')
        self.ax3.yaxis.tick_left()
        self.ax3.yaxis.set_label_position('left')
        self.ax3.yaxis.label.set_color('c')
        self.ax3.tick_params(axis='y', colors='c')

        for spine in self.ax3.spines.values():
            spine.set_edgecolor('w' if darkmode else 'k')

        for axItr in [self.ax2]:
            axItr.grid(True, alpha=.5)
            axItr.yaxis.set_label_position('right')
            axItr.yaxis.tick_right()
#         self.ax4 = fig.add_subplot(224, projection=ccrs.NearsidePerspective(central_longitude=-74, central_latitude=40.5))
        self.ax4 = plt.subplot2grid((2, 2), (1, 0), colspan=2, projection=ccrs.Robinson())
        self.ax4TimeToUpdate = datetime.now()
        self.ax4TimeToGeoLoc = datetime.now()
        self.ax4GeoLoc = CitiesCoords['New York']
        # initialize
        self.sysStats = updateSysStats(self.sysStats)
        self.lines = [[], {}, [], []]
        sysStatsX = extractSysStats(self.sysStats, 'time')
        #CPU percentage
        cpuPercent = extractSysStats(self.sysStats, 'cpuPercent')
        #CPU temperature
        cpuTempCel = extractSysStats(self.sysStats, 'cpuTempCel')
        line, = self.ax2.plot(sysStatsX, cpuTempCel, '2:r', ms=3, lw=.5)
        self.lines[1]['cpuTempCel'] = line
        #memory percertange
        memPercent = extractSysStats(self.sysStats, 'memPercent')
        line, = self.ax3.plot(sysStatsX, memPercent, '.-c', ms=3, lw=.5)
        self.lines[1]['memPercent'] = line
        #globe
#         self.ax4.stock_img()
        self.http = urllib3.PoolManager()
        
        
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
        self.lines[1]['cpuTempCel'].set_data(sysStatsX, cpuTempCel)
        #memory percertange
        memPercent = extractSysStats(self.sysStats, 'memPercent')
        self.lines[1]['memPercent'].set_data(sysStatsX, memPercent)
        #globe
        if max(self.sysStats.keys())>self.ax4TimeToUpdate:
            if max(self.sysStats.keys())>self.ax4TimeToGeoLoc:
                try:
                    geolocResponse = self.http.request('GET', 'http://ipinfo.io/json')
                    geolocData = json.loads(geolocResponse.data)
                    self.ax4GeoLoc = eval(geolocData['loc'])[0:2]
                except:
                    self.ax4GeoLoc = self.ax4GeoLoc
            
            self.ax4.cla()
            self.ax4.set_global()
            self.ax4.coastlines()
#             self.ax4.stock_img()
#             self.ax4.background_img(name='BM', resolution='low')
            utcnow = datetime.utcnow()
            self.ax4.add_feature(Nightshade(utcnow, alpha=.15))
            scatterLongitudes = [x[1] for x in CitiesCoords.values()]#+[self.ax4GeoLoc[1]]
            scatterLatitudes = [x[0] for x in CitiesCoords.values()]#+[self.ax4GeoLoc[0]]
            scatterColors = ['c']*len(CitiesCoords)#+['r']
            self.ax4.scatter(scatterLongitudes, scatterLatitudes, s=10, c=scatterColors, alpha=.8, transform=ccrs.PlateCarree())
            self.ax4.gridlines(crs=ccrs.PlateCarree(), xlocs=[self.ax4GeoLoc[1]], ylocs=[self.ax4GeoLoc[0]], color='y', alpha=.4)
            self.ax4.plot([self.ax4GeoLoc[1]], [self.ax4GeoLoc[0]], ms=7, c='r', transform=ccrs.PlateCarree(),
                          **{'marker': '$\\bigoplus$', 'linestyle': '', 'markeredgewidth': .1})
            for (k,v) in CitiesCoords.items():
                self.ax4.text(v[1]+3, v[0]-3, k, fontsize='xx-small', color='b', alpha=.95, horizontalalignment='left',
                              verticalalignment='top', transform=ccrs.Geodetic())
            sun = Sun(self.ax4GeoLoc[0], self.ax4GeoLoc[1])
            today = utcnow.date()
            sunrises = [sun.get_sunrise_time(d) for d in [today-timedelta(days=1), today, today+timedelta(days=1)]]
            sunsets = [sun.get_sunset_time(d) for d in [today-timedelta(days=1), today, today+timedelta(days=1)]]
            sunTimes = sunrises+sunsets
            sunTimes = [d.replace(tzinfo=None) for d in sunTimes]
            sunTimes.sort()
            sunTimeLast = [t for t in sunTimes if t<utcnow.replace(tzinfo=None)][-1]
            sunTimeNext = [t for t in sunTimes if t>=utcnow.replace(tzinfo=None)][0]
            sunHoursDeltas = [t-utcnow for t in [sunTimeLast, sunTimeNext]]
            sunHours = [td.days*24+td.seconds/3600 for td in sunHoursDeltas]
            sunHHMMs = ['{:+03.0f}:{:02.0f}'.format(math.trunc(sh), 60*abs(sh-math.trunc(sh))) for sh in sunHours]
            meStrTxts = [
                self.ax4.text(self.ax4GeoLoc[1]+txtPosShiftHor, self.ax4GeoLoc[0]+3, meStr, fontsize='xx-small', fontweight='normal', color='m',
                                     alpha=.99, horizontalalignment=txtPosAlignHor, transform=ccrs.Geodetic())
                for (meStr, txtPosAlignHor, txtPosShiftHor) in zip(sunHHMMs, ['right', 'left'], [-3, 3])
            ]
            for txtObj in meStrTxts: txtObj.set_path_effects([PathEffects.withStroke(linewidth=2, foreground='w')])
            self.ax4TimeToUpdate += timedelta(seconds=300)
            self.ax4TimeToGeoLoc += timedelta(seconds=1200)
        

fig = plt.figure('Dashboard', figsize=(10, 7), facecolor='w')
animate = updateAxes(fig)
anim = animation.FuncAnimation(fig, animate, interval=1000, repeat=False)
plt.show()