import functools, os, json, psutil
import time, math, datetime
import digitalio, board
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
# import matplotlib.ticker as mticker
from PIL import Image, ImageDraw, ImageFont
from adafruit_rgb_display import st7789
from adafruit_rgb_display.rgb import color565
import yfinance as yf
import pandas as pd
# import ystockquote, stockquotes, yahoo_fin

width = height = 240
rotation = 270
time_interval_button = .1

cs_pin, dc_pin = board.CE0, board.D25
backlight_pin = board.D22
button_a_pin, button_b_pin = board.D23, board.D24

relfp_image_disp = 'data/image_disp.jpg'
relfp_mkt_data_query_settings = './settings/markets_query_settings.csv'
relfp_mkt_data_plot_settings = './settings/mktdata_plot_settings.json'
relfp_mkt_data = './data/mkt_data.pkl'

mandelbrot_scan_params = {
    'radius_limits': {'min': .1, 'max': 1.5},
    'radius_change_rate': 1.2,
    'pan_vel_to_radius_ratio': (.1, 1 / math.pi),
    'extent': (-2, -1.5, 1, 1.5)
}


def memfunc_decorator(min_time_inter_update, min_time_to_consume=0):
    def decorate_inner(func):
        @functools.wraps(func)
        def wrapper_dec(*args, **kwargs):
            ref = args[0]
            _time = time.time()

            if _time > ref.time_to_update or ref.mode != ref.mode_prev:
                retval = func(*args, **kwargs)
                ref.time_to_update = time.time() + min_time_inter_update
                ref.mode_prev = ref.mode
            else:
                retval = None

            _time = time.time() - _time

            if _time < min_time_to_consume:
                time.sleep(min_time_to_consume - _time)

            return retval
        return wrapper_dec
    return decorate_inner


def query_mkt_data(mktdata_settings, relfp_md=relfp_mkt_data):
    try:
        mktdata = pd.read_pickle(relfp_md)
        today = datetime.date.today()
        if mktdata.index.max().date() >= today:
            return mktdata
    except:
        mktdata = pd.DataFrame()

    tickers = mktdata_settings.index.to_list()
    mktdata_ = yf.download(' '.join(tickers), period='10y', interval='1d')
    mktdata = pd.concat([mktdata, mktdata_]).drop_duplicates()
    mktdata.to_pickle(relfp_md)

    return mktdata


class tftDisp:
    def __init__(self, baudrate=64000000,
        width=width, height=height, rotation=rotation, x_offset=0, y_offset=80,
        cs_pin=cs_pin, dc_pin=dc_pin, reset_pin=None, backlight_pin=backlight_pin,
        button_a_pin=button_a_pin, button_b_pin=button_b_pin,
        spi=None,
        relfp_mktdata_settings=relfp_mkt_data_query_settings
    ):
        self.mode_prev = 0
        self.mode = 0
        self.width = width
        self.height = height
        self.rotation = rotation
        self.time_to_update = time.time()
        self.time_to_read_button = time.time()

        self.disp_mode_fill = 0
        self.mandelbrot_extent_params = {
            'center': [-.5, 0],
            'radius': 1.5,
            'radius_rate': 1 / 1.2,
            'pan_vel_to_radius_ratio': [.1, 1 / math.pi],
        }

        self.mktdata = None
        self.mktdata_settings = pd.read_csv(relfp_mktdata_settings, sep=',', index_col='ticker')
        self.mktdata_groupid = 0
        with open(relfp_mkt_data_plot_settings, 'r') as f:
            self.mktdata_plot_settings = json.load((f))

        spi = board.SPI() if spi is None else spi
        cs_io = digitalio.DigitalInOut(cs_pin)
        dc_io = digitalio.DigitalInOut(dc_pin)

        self.button_a = digitalio.DigitalInOut(button_a_pin)
        self.button_b = digitalio.DigitalInOut(button_b_pin)
        self.button_a.switch_to_input()
        self.button_b.switch_to_input()

        self.backlight = digitalio.DigitalInOut(backlight_pin)
        self.backlight.switch_to_output()
        self.backlight.value = True

        self.disp = st7789.ST7789(
            spi,
            cs=cs_io, dc=dc_io, rst=reset_pin, baudrate=baudrate,
            width=width, height=height, x_offset=x_offset, y_offset=y_offset
        )

    @memfunc_decorator(30)
    def clear(self):
        self.backlight.value = False
        self.disp.fill(0)

    @memfunc_decorator(.25)
    def disp_mandelbrot(self, scan_params=mandelbrot_scan_params):
        self.backlight.value = True

        extent = (
            self.mandelbrot_extent_params['center'][0] - self.mandelbrot_extent_params['radius'],
            self.mandelbrot_extent_params['center'][1] - self.mandelbrot_extent_params['radius'],
            self.mandelbrot_extent_params['center'][0] + self.mandelbrot_extent_params['radius'],
            self.mandelbrot_extent_params['center'][1] + self.mandelbrot_extent_params['radius'],
        )

        if extent[0] < scan_params['extent'][0]:
            self.mandelbrot_extent_params['pan_vel_to_radius_ratio'][0] = scan_params['pan_vel_to_radius_ratio'][0]
        if extent[1] < scan_params['extent'][1]:
            self.mandelbrot_extent_params['pan_vel_to_radius_ratio'][1] = scan_params['pan_vel_to_radius_ratio'][1]
        if extent[2] > scan_params['extent'][2]:
            self.mandelbrot_extent_params['pan_vel_to_radius_ratio'][0] = -scan_params['pan_vel_to_radius_ratio'][0]
        if extent[3] > scan_params['extent'][3]:
            self.mandelbrot_extent_params['pan_vel_to_radius_ratio'][1] = -scan_params['pan_vel_to_radius_ratio'][1]

        extent = [max(xy, lmt) if ix < 2 else min(xy, lmt)
                  for ix, xy, lmt in zip(range(4), extent, scan_params['extent'])]

        if self.mandelbrot_extent_params['radius'] > scan_params['radius_limits']['max']:
            self.mandelbrot_extent_params['radius_rate'] = 1 / scan_params['radius_change_rate']
        if self.mandelbrot_extent_params['radius'] < scan_params['radius_limits']['min']:
            self.mandelbrot_extent_params['radius_rate'] = scan_params['radius_change_rate']

        self.mandelbrot_extent_params['radius'] *= self.mandelbrot_extent_params['radius_rate']
        self.mandelbrot_extent_params['center'][0] += \
            self.mandelbrot_extent_params['pan_vel_to_radius_ratio'][0] * self.mandelbrot_extent_params['radius']
        self.mandelbrot_extent_params['center'][1] += \
            self.mandelbrot_extent_params['pan_vel_to_radius_ratio'][1] * self.mandelbrot_extent_params['radius']

        image = Image.effect_mandelbrot((self.width, self.height), tuple(extent), 100).convert('RGBA')
        self.disp.image(image, self.rotation)

    @memfunc_decorator(60)
    def disp_fill(self):
        self.backlight.value = True
        if 0 == self.disp_mode_fill:
            self.disp.fill(color565(0, 255, 255))
        elif 1 == self.disp_mode_fill:
            self.disp.image(Image.effect_noise((self.width, self.height), 50).convert('RGBA'), self.rotation)
        elif 2 == self.disp_mode_fill:
            self.disp.image(Image.radial_gradient('L').convert('RGBA').resize((self.width, self.height), Image.BICUBIC))
        elif 3 == self.disp_mode_fill:
            self.disp.image(Image.linear_gradient('L').convert('RGBA').resize((self.width, self.height), Image.BICUBIC))

        self.disp_mode_fill += 1
        self.disp_mode_fill %= 4

    @memfunc_decorator(1)
    def disp_system_stats(self):
        date_local = time.strftime('%d%b%y')
        time_local = time.strftime(' %H:%M%p')
        cpu_pct = 'CPU: {:.0f}%'.format(psutil.cpu_percent(interval=.2, percpu=False))
        mem_stats = 'Mem: {:.1f}%'.format(psutil.virtual_memory().percent)
        tmp_sensors = 'Temp: {:.1f} C'.format(psutil.sensors_temperatures()['cpu_thermal'][0].current)

        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        self.backlight.value = True
        image = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        x = y = 0
        draw.text((x, y), date_local, font=font, fill='#FFFFFF')
        x += font.getsize(date_local)[0]
        draw.text((x, y), time_local, font=font, fill='#00FFFF')
        x = 0
        y += font.getsize(time_local)[1]
        draw.text((x, y), cpu_pct, font=font, fill='#FFFF00')
        y += font.getsize(cpu_pct)[1]
        draw.text((x, y), mem_stats, font=font, fill='#00FF00')
        y += font.getsize(mem_stats)[1]
        draw.text((x, y), tmp_sensors, font=font, fill='#FF0000')
        self.disp.image(image, self.rotation)

    @memfunc_decorator(30)
    def disp_markets(self):
        if self.mktdata is None:
            self.mktdata = query_mkt_data(self.mktdata_settings)

        mktdata = self.mktdata.loc[:, 'Adj Close']

        mktdata_groups = self.mktdata_settings.loc[:, 'group'].unique()
        group = mktdata_groups[math.floor(self.mktdata_groupid / len(self.mktdata_plot_settings['lookbacks']))]
        settings_ = self.mktdata_settings.loc[self.mktdata_settings['group'] == group]
        tickers_ = settings_.index.to_list()
        to_scale = max(settings_.loc[:, 'normalize'].to_list())

        mktdata_ = mktdata.loc[:, tickers_]
        lookback = self.mktdata_plot_settings['lookbacks'][
            self.mktdata_groupid % len(self.mktdata_plot_settings['lookbacks'])
        ]
        today = datetime.date.today()
        lookback_start = today - datetime.timedelta(days=lookback['days'])
        mktdata_ = mktdata_.loc[lookback_start:, :]
        if to_scale:
            mktdata_ = mktdata_ / mktdata_.iloc[1, :]

        fig, ax = plt.subplots(figsize=(4, 4))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=lookback['x_bymonth']))
        ax.xaxis.set_major_formatter(mdates.DateFormatter(lookback['x_dateformatter']))
        ax.grid(True, which='major')
        mktdata_.plot(grid=True, ax=ax,
            style=settings_.loc[:, 'linestyle'].to_dict(),
            color=settings_.loc[:, 'color'].to_dict()
        )
        plt.savefig('./' + relfp_image_disp)
        fp_image_disp = os.path.join(os.getcwd(), relfp_image_disp)
        image = Image.open(fp_image_disp).convert('RGBA').resize((self.width, self.height), Image.BICUBIC)
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        draw.text((0, 0), lookback['name'], font=font, fill='#FFA500')
        self.disp.image(image, self.rotation)

        self.mktdata_groupid += 1
        self.mktdata_groupid %= mktdata_groups.size * len(self.mktdata_plot_settings['lookbacks'])


if __name__ == '__main__':
    tft = tftDisp()
    buffer_mode = 2

    while True:
        if time.time() > tft.time_to_read_button:
            tft.time_to_read_button = time.time() + time_interval_button
            button_a, button_b = not tft.button_a.value, not tft.button_b.value

            if (button_a and button_b) or ((button_a or button_b) and -buffer_mode >= tft.mode):
                tft.mode = -tft.mode - buffer_mode
            elif button_a:
                tft.mode += 1
            elif button_b:
                tft.mode -= 1

            if -buffer_mode < tft.mode:
                tft.mode %= 4

        print('mode ' + repr(tft.mode) + '\t' + repr(time.time()))

        if -buffer_mode >= tft.mode:
            tft.clear()
        elif 0 == tft.mode:
            tft.disp_system_stats()
        elif 1 == tft.mode:
            tft.disp_mandelbrot()
        elif 2 == tft.mode:
            tft.disp_fill()
        elif 3 == tft.mode:
            tft.disp_markets()
