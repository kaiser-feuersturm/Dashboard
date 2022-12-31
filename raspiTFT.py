import functools, os, json, psutil, calendar
import time, math, datetime, random
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

calendar.setfirstweekday(calendar.SUNDAY)


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


def query_mkt_data(mktdata_settings, filepath_mktdata, cols_filter=None):
    to_download = True
    try:
        mktdata = pd.read_pickle(filepath_mktdata)
        today = datetime.date.today()
        if mktdata.index.max().date() >= today or time.time() - os.path.getmtime(filepath_mktdata) < 7200:
            to_download = False
    except:
        mktdata = pd.DataFrame()

    if to_download:
        tickers = mktdata_settings.index.to_list()
        mktdata_ = yf.download(' '.join(tickers), period='10y', interval='1d')
        mktdata_index = mktdata_.index.difference(mktdata.index)
        mktdata_ = mktdata_.loc[mktdata_index, :]
        mktdata = pd.concat([mktdata, mktdata_]).sort_index().drop_duplicates()
        mktdata.to_pickle(filepath_mktdata)

    retval = mktdata if cols_filter is None else mktdata.loc[:, cols_filter]
    return retval


def filepath_from_relfp(relfp):
    dir_file = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(dir_file, relfp)


def pil_draw_text_calendar(draw, xy, size, font, consistent_sizing=True,
                           color_weekend='#FF0000', color_weekday='#FFFFFF',
                           align_to_right=True, mark_today=None):
    date_today = datetime.date.today()
    str_cmp = '{}'.format(date_today.day) if mark_today is not None else '__wtf__'
    cal_matrix = calendar.monthcalendar(date_today.year, date_today.month)
    str_matrix = [[calendar.TextCalendar.formatweekday(None, (ix - 1) % 7, 2) for ix in range(7)]]
    str_matrix += [['{}'.format(d) if d > 0 else '' for d in w] for w in cal_matrix]
    x, y = xy
    x_size, y_size = size
    x_size /= 7
    y_size /= 6 if consistent_sizing else len(str_matrix)
    for iw, w in enumerate(str_matrix):
        for id, d in enumerate(w):
            x_offset = x_size - font.getbbox(d)[2] if align_to_right else 0
            x_, y_ = x + id * x_size + x_offset, y + y_size * iw

            if d == str_cmp:
                bbox = font.getbbox(d)
                mg = mark_today.get('margin', 2)
                draw.rectangle(
                    [x_ + bbox[0] - mg, y_ + bbox[1] - mg, x_ + bbox[2] + mg, y_ + bbox[3] + mg],
                    outline=mark_today.get('outline', '#00FFFF'),
                    fill=mark_today.get('fill', None), width=mark_today.get('width', 1)
                )

            draw.text((x_, y_), d, font=font, fill=color_weekend if id < 1 or id > 5 else color_weekday)

    return (x + size[0], y + size[1])

def pil_draw_text_sys_stats(draw, xy, font, align_segments=True):
    cpu_pct = 'CPU: {:.0f}%'.format(psutil.cpu_percent(interval=.2, percpu=False))
    mem_stats = 'Mem: {:.1f}%'.format(psutil.virtual_memory().percent)
    tmp_sensors = 'Temp: {:.1f} C'.format(psutil.sensors_temperatures()['cpu_thermal'][0].current)

    x, y = xy
    x_max = x
    for str_, fill_ in zip(
        [cpu_pct, mem_stats, tmp_sensors],
        ['#FFFF00', '#00FF00', '#FF0000']
    ):
        draw.text((x, y), str_, font=font, fill=fill_)
        bbox = font.getbbox(str_)
        x_max = max(x_max, bbox[2])
        y += bbox[3]

    return (x_max, y)

class RaspiTftDisplay:
    def __init__(
        self, baudrate=64000000,
        width=240, height=240, rotation=0, x_offset=0, y_offset=80,
        cs_pin=None, dc_pin=None, reset_pin=None, backlight_pin=None,
        button_a_pin=None, button_b_pin=None,
        spi=None,
        relfp_mktdata_query_settings=None,
        relfp_mktdata_plot_settings=None,
        relfp_mktdata=None,
        relfp_image_disp=None,
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
        self.filepath_mktdata = filepath_from_relfp(relfp_mktdata)
        self.filepath_image_disp = filepath_from_relfp(relfp_image_disp)
        self.mktdata_settings = pd.read_csv(
            filepath_from_relfp(relfp_mktdata_query_settings),
            sep=',', index_col='ticker'
        )
        self.mktdata_groupid = 0
        with open(filepath_from_relfp(relfp_mktdata_plot_settings), 'r') as f:
            self.mktdata_plot_settings = json.load(f)

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
        if self.backlight.value:
            self.disp_fill(0)
            self.backlight.value = False
        else:
            pass


    @memfunc_decorator(.25)
    def disp_mandelbrot(self, scan_params=None):
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

    @memfunc_decorator(3)
    def disp_fill(self):
        self.backlight.value = True
        if 0 == self.disp_mode_fill:
            self.disp.fill(color565(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        elif 1 == self.disp_mode_fill:
            self.disp.image(Image.effect_noise((self.width, self.height), 50).convert('RGBA'), self.rotation)
        elif 2 == self.disp_mode_fill:
            self.disp.image(Image.radial_gradient('L').convert('RGBA').resize(
                (self.width, self.height), Image.Resampling.BICUBIC)
            )
        elif 3 == self.disp_mode_fill:
            self.disp.image(Image.linear_gradient('L').convert('RGBA').resize(
                (self.width, self.height), Image.Resampling.BICUBIC)
            )
        elif 4 == self.disp_mode_fill:
            self.disp.image(Image.effect_mandelbrot((self.width, self.height), (-2, -1.5, 1, 1.5), 100).convert('RGBA'))

        self.disp_mode_fill += 1
        self.disp_mode_fill %= 4

    @memfunc_decorator(1)
    def disp_system_stats(self):
        date_local = time.strftime('%d%b%y')
        time_local = time.strftime('   %H:%M%p')

        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
        self.backlight.value = True
        image = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        x = y = 0
        draw.text((x, y), date_local, font=font, fill='#FFFFFF')
        x += font.getbbox(date_local)[2]
        draw.text((x, y), time_local, font=font, fill='#00FFFF')
        y += font.getbbox(time_local)[3]

        margin_cal = 20
        xy_ = pil_draw_text_calendar(draw, (margin_cal, y + 5), (self.width - 2 * margin_cal, 80),
                               font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 11),
                               mark_today={'outline': '#FFFF00'})
        pil_draw_text_sys_stats(draw, (0, xy_[1] + 10), font)
        self.disp.image(image, self.rotation)

    @memfunc_decorator(15)
    def disp_markets(self):
        if self.mktdata is None:
            self.mktdata = query_mkt_data(self.mktdata_settings, self.filepath_mktdata, cols_filter='Adj Close')

        mktdata_groups = self.mktdata_settings.loc[:, 'group'].unique()
        group = mktdata_groups[math.floor(self.mktdata_groupid / len(self.mktdata_plot_settings['lookbacks']))]
        settings_ = self.mktdata_settings.loc[self.mktdata_settings['group'] == group]
        tickers_ = settings_.index.to_list()
        to_scale = max(settings_.loc[:, 'normalize'].to_list())

        mktdata_ = self.mktdata.loc[:, tickers_]
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
        mktdata_.plot(
            grid=True, ax=ax,
            style=settings_.loc[:, 'linestyle'].to_dict(),
            color=settings_.loc[:, 'color'].to_dict()
        )

        fig.canvas.draw()
        image = Image.frombytes('RGB', fig.canvas.get_width_height(), fig.canvas.tostring_rgb()).resize(
            (self.width, self.height), Image.Resampling.BICUBIC
        )
        plt.close('all')

        x = 0
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        draw.text((0, 0), lookback['name'], font=font, fill='#16537E')
        if to_scale:
            x += font.getbbox(lookback['name'] + '   ')[2]
            draw.text((x, 0), 'scaled', font=font, fill='#FF00FF')

        self.disp.image(image, self.rotation)

        self.mktdata_groupid += 1
        self.mktdata_groupid %= mktdata_groups.size * len(self.mktdata_plot_settings['lookbacks'])


if __name__ == '__main__':
    relfp_mkt_data_query_settings = 'settings/markets_query_settings.csv'
    relfp_mkt_data_plot_settings = 'settings/mktdata_plot_settings.json'
    relfp_mkt_data = 'data/mkt_data.pkl'
    relfp_image_disp = 'data/image_disp.jpg'

    width = height = 240
    rotation = 180
    time_interval_button = .2

    cs_pin, dc_pin = board.CE0, board.D25
    backlight_pin = board.D22
    button_a_pin, button_b_pin = board.D23, board.D24

    tft = RaspiTftDisplay(
        baudrate=64000000,
        width=width, height=height, rotation=rotation, x_offset=0, y_offset=80,
        cs_pin=cs_pin, dc_pin=dc_pin, reset_pin=None, backlight_pin=backlight_pin,
        button_a_pin=button_a_pin, button_b_pin=button_b_pin,
        relfp_mktdata_query_settings=relfp_mkt_data_query_settings,
        relfp_mktdata_plot_settings=relfp_mkt_data_plot_settings,
        relfp_mktdata=relfp_mkt_data,
        relfp_image_disp=relfp_image_disp
    )
    tft.mandelbrot_extent_params = {
        'center': [-1.4002, 0],
        'radius': 1.5,
        'radius_rate': 1 / 1.2,
        'pan_vel_to_radius_ratio': [1e-5, 0],
    }
    mandelbrot_scan_params = {
        'radius_limits': {'min': .1, 'max': 1.5},
        'radius_change_rate': 1.2,
        'pan_vel_to_radius_ratio': (1e-5, 0),
        'extent': (-1.4011 - 1.5, -1.5, 1.4002 + 1.5, 1.5)
    }

    buffer_mode = 2

    print('initialized dashboard object. stepping into (intended) infinite loop now...')
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

        # print('mode ' + repr(tft.mode) + '\t' + repr(time.time()))

        if -buffer_mode >= tft.mode:
            tft.clear()
        elif 0 == tft.mode:
            tft.disp_system_stats()
        elif 1 == tft.mode:
            tft.disp_markets()
        elif 2 == tft.mode:
            tft.disp_fill()
        elif 3 == tft.mode:
            tft.disp_mandelbrot(scan_params=mandelbrot_scan_params)
