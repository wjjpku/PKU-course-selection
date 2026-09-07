#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# filename: recognizer.py
# modified: 2020-02-16

import os
import time
import ddddocr
from autoelective.const import CAPTCHA_LABELS_FILE, CNN_MODEL_FILE

class Captcha(object):

    __slots__ = ['_code','_im_data']

    def __init__(self, code, im_data):
        self._code = code
        self._im_data = im_data

    @property
    def code(self):
        return self._code

    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__,
            self._code,
        )

    def save(self, folder):
        code = self._code
        data = self._im_data
        timestamp = int(time.time() * 1000)

        filepath = os.path.join(folder, "%s_%d.jpg" % (code, timestamp))
        with open(filepath, 'wb') as fp:
            fp.write(data)


class CaptchaRecognizer(object):

    def __init__(self, model_file=CNN_MODEL_FILE, charsets_path=CAPTCHA_LABELS_FILE):
        self._model = ddddocr.DdddOcr(det=False, ocr=False, import_onnx_path=model_file, charsets_path=charsets_path , show_ad=False)

    def recognize(self, im_data):
        assert isinstance(im_data, bytes)
        code = self._model.classification(im_data)

        return Captcha(code, im_data)
