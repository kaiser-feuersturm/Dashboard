import functools
import time
import subprocess
import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
from adafruit_rgb_display import st7789
from adafruit_rgb_display.rgb import color565

width = height = 240
rotation = 90

cs_pin, dc_pin = board.CE0, board.D25
backlight_pin = board.D22
button_a_pin, button_b_pin = board.D23, board.D24


def memfunc_decorator(min_time_inter_update, min_time_to_consume=.5):
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


if __name__ == '__main__':
    tft = tft_disp()

    while True:
        if tft.button_a.value and tft.button_b.value:
            tft.clear()
        elif tft.button_a.value:
            tft.mode += 1
        elif tft.button_b.value:
            tft.mode -= 1

        tft.mode = tft.mode % 3
        print('mode ' + repr(tft.mode) + '\t' + repr(time.time()))

        if 0 == tft.mode:
        #     tft.disp_mandelbrot()
        # elif 1 == tft.mode:
            tft.fill()
        elif 2 == tft.mode:
            tft.clear()
