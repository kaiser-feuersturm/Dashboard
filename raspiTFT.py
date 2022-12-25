import functools
import time, datetime
import subprocess
import digitalio
import board
import psutil
from PIL import Image, ImageDraw, ImageFont
from adafruit_rgb_display import st7789
from adafruit_rgb_display.rgb import color565

width = height = 240
rotation = 90
time_interval_button = .8

cs_pin, dc_pin = board.CE0, board.D25
backlight_pin = board.D22
button_a_pin, button_b_pin = board.D23, board.D24


def memfunc_decorator(min_time_inter_update, min_time_to_consume=0):
    def decorate_inner(func):
        @functools.wraps(func)
        def wrapper_dec(*args, **kwargs):
            _time = time.time()

            retval = func(*args, **kwargs)
            ref = args[0]
            ref.time_to_update = time.time() + min_time_inter_update

            _time = time.time() - _time

            if _time < min_time_to_consume:
                time.sleep(min_time_to_consume - _time)

            return retval
        return wrapper_dec
    return decorate_inner


class tft_disp:
    def __init__(self, baudrate=64000000,
        width=width, height=height, rotation=rotation, x_offset=0, y_offset=80,
        cs_pin=cs_pin, dc_pin=dc_pin, reset_pin=None, backlight_pin=backlight_pin,
        button_a_pin=button_a_pin, button_b_pin=button_b_pin,
        spi=None
    ):
        self.mode = 0
        self.width = width
        self.height = height
        self.rotation = rotation
        self.time_to_update = time.time()
        self.time_to_read_button = time.time()

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

        self.disp = st7789.ST7789(spi,
            cs=cs_io, dc=dc_io, rst=reset_pin, baudrate=baudrate,
            width=width, height=height, x_offset=x_offset, y_offset=y_offset
        )

    @memfunc_decorator(30)
    def clear(self):
        self.backlight = False
        image = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, self.height), outline=0, fill=(0,0,0))
        self.disp.image(image, self.rotation)

    @memfunc_decorator(30)
    def fill(self):
        self.backlight = True
        self.disp.fill(color565(0, 255, 0))

    @memfunc_decorator(30)
    def disp_mandelbrot(self):
        self.backlight = True
        image = Image.effect_mandelbrot((self.width, self.height), (0, 0, self.width, self.height), 100)
        self.disp.image(image, self.rotation)

    @memfunc_decorator(1)
    def disp_system_stats(self):
        time_local = repr(datetime.datetime.now())
        cpu_pct = repr(psutil.cpu_percent(interval=1, percpu=True))
        mem_stats = repr(psutil.virtual_memory().percent)
        tmp_sensors = repr(psutil.sensors_temperatures()['cpu_thermal'][0].current)

        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        self.backlight = True
        image = Image.new('RGB', (self.width, self.height))
        draw = ImageDraw.Draw(image)
        x = y = 0
        draw.text((x,y), time_local, font=font, fill='#FFFFFF')
        y += font.getsize(time_local)[1]
        draw.text((x,y), cpu_pct, font=font, fill='#FFFF00')
        y += font.getsize(cpu_pct)[1]
        draw.text((x,y), mem_stats, font=font, fill='#00FF00')
        y += font.getsize(mem_stats)[1]
        draw.text((x,y), tmp_sensors, font=font, fill='#0000FF')



if __name__ == '__main__':
    tft = tft_disp()

    while True:
        if time.time() > tft.time_to_read_button:
            tft.time_to_read_button = time.time() + time_interval_button
            button_a, button_b = tft.button_a.value, tft.button_b.value
            print('reading button: ' + repr(time.time()) + repr(button_a) + ' ' + repr(button_b))

            if button_a and button_b:
                tft.clear()
            elif button_a:
                tft.mode += 1
            elif button_b:
                tft.mode -= 1

        tft.mode = tft.mode % 3
        print('mode ' + repr(tft.mode) + '\t' + repr(time.time()))

        if 0 == tft.mode:
            tft.disp_system_stats()
        elif 1 == tft.mode:
            tft.fill()
        elif 2 == tft.mode:
            tft.clear()
