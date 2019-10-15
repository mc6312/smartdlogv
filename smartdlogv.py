#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" smartdlogv.py

    Copyright 2019 mc6312

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License version 3
    as published by the Free Software Foundation.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>."""


import sys
import csv
import os, os.path
import re
import datetime
import argparse
import json
from collections import namedtuple
from traceback import format_exception


TITLE = 'Smartd Log Viewer'
VERSION = '1.2.3-1'
TITLE_VERSION = '%s v%s' % (TITLE, VERSION)

RX_FNAME = re.compile(r'^attrlog\.(.*?)\..*?\.csv', re.UNICODE)

RX_DEVNAME = re.compile(r'^(ata|scsi)-(.*)$')
RX_DEVPART = re.compile(r'.*?-part\d+$')

MAX_LOG_RECORDS = 20

LOG_DIR = '/var/lib/smartmontools'
LOG_TIMEFORMAT = '%Y-%m-%d %H:%M:%S'

# 5     Reallocated Sectors Count
# 190   Airflow Temperature (пока игнорируем)
# 191   G-sense error rate
# 196   Reallocation Event Count
# 197   Current Pending Sector Count
# 198   Uncorrectable Sector Count
# 200   Multi-Zone Error Rate
# 220   Disk Shift

WATCH_ATTRS = {5, 191, 196, 197, 198, 200, 220}


smart_log_rec = namedtuple('smart_log_rec', 'timestamp attrs')
# запись журнала атрибутов S.M.A.R.T, где:
# timestamp - экземпляр datetime.datetime
# attrs     - словарь, где ключи - номера атрибутов, а значения -
#             экземпляры smart_attr


class smart_attr():
    """Значения атрибута, где:
value     - нормализованное значение атрибута
valdelta  - разница с предыдущим нормализованным значением
raw       - необработанное значение атрибута
rawdelta  - разница с предыдущим необработанным значением"""
    __slots__ = 'value', 'valdelta', 'raw', 'rawdelta'

    def __init__(self, v, vd, r, rd):
        self.value = v
        self.valdelta = vd
        self.raw = r
        self.rawdelta = rd

    def compute_deltas(self, other):
        """Устанавливает значения полей valdelta и rawdelta
        в зависимости от значений из other.
        Возвращает булевское значение - True, если хотя бы одно
        из полей self.*delta ненулевое."""

        self.valdelta = self.value - other.value
        self.rawdelta = self.raw - other.raw

        return self.valdelta != 0 or self.rawdelta != 0


device_name = namedtuple('device_name', 'filename modelname')
# имя дискового устройства, где:
# filename  - имя реального файла устройства в каталоге /dev/ (только имя!)
# modelname - строка вида MODEL_SERIAL (аналогично содержимому /dev/disk/by-id)


class SMART_Log():
    def __init__(self, fpath, devname, onlyAttrs, shorten):
        """Разбор журнала атрибутов S.M.A.R.T.
        fpath       - полный путь к файлу журнала атрибутов,
        devname     - экземпляр device_name,
        onlyAttrs   - множество целых; если множество не пустое - учитывать
                      только указанные в нём атрибуты,
        shorten     - сократить лог до MAX_LOG_RECORDS.

        В списке log сохранется список экземпляров smart_log_rec,
        а значения - словари, в которых ключи - номера атрибутов, а значения -
        экземпляры smart_attr."""

        self.log = []
        self.devname = devname
        self.nrawrecords = 0

        # ключи - номера атрибутов, значения - экземпляры smart_attr
        # для сравнения с очередными прочитанными из лога и для вычисления дельты
        lastvalues = dict()

        firstrecord = True

        with open(fpath, 'r') as f:
            csvf = csv.reader(f, delimiter=';')

            for ixrec, rec in enumerate(csvf, 1):
                #
                # разбор очередной записи
                #
                nflds = len(rec) - 2
                if (nflds % 3) != 0:
                    raise SyntaxError('Invalid number of fields of record #%d of file "%s"' % (ixrec, fpath))

                # формат записей проверяем - может, лог поломат?

                # здесь - дата в формате YYYY-MM-DD HH:MM:SS
                try:
                    date = datetime.datetime.strptime(rec[0], LOG_TIMEFORMAT)
                except ValueError as ex:
                    raise ValueError('Invalid date/time field in record #%d of file "%s" - %s' % (ixrec, fpath, str(ex)))

                adict = dict()
                ndeltas = 0

                # группы по три целых числа - attribute, value, raw value
                for ixattr, sattrv in enumerate(zip(*[iter(rec[1:-1])]*3), 1):
                    try:
                        nattr, nvalue, nraw = map(lambda s: int(s.strip()), sattrv)
                    except ValueError:
                        raise ValueError('Invalid attribute(s) in group #%d at record #%d of file "%s"' % (ixattr, ixrec, fpath))

                    # отбрасываем ненужные атрибуты
                    if nattr not in onlyAttrs:
                        continue

                    curattr = smart_attr(nvalue, 0, nraw, 0)

                    if nattr in lastvalues:
                        if curattr.compute_deltas(lastvalues[nattr]):
                            lastvalues[nattr] = curattr
                            ndeltas += 1
                    else:
                        lastvalues[nattr] = curattr

                    adict[nattr] = curattr

                self.nrawrecords += 1

                if firstrecord or ndeltas > 0:
                    # добавляем в список:
                    # - первую запись из файла
                    # - только те последующие записи, где есть изменения атрибутов
                    self.log.append(smart_log_rec(date, adict))

                    firstrecord = False

        #
        # если требуется сокращённый журнал...
        #
        loglen = len(self.log)
        if shorten and loglen > MAX_LOG_RECORDS:
            # ...удаляем лишние записи...
            del self.log[1:-(MAX_LOG_RECORDS - 1)]

            # ...и пересчитываем дельты для оставшихся
            lastvalues = self.log[0].attrs

            for rec in self.log[1:]:
                for nattr in rec.attrs:
                    if nattr in lastvalues:
                        rec.attrs[nattr].compute_deltas(lastvalues[nattr])

    def print_table(self):
        """Вывод в stdout содержимого журнала в виде текстовой таблицы."""

        print('%s (%s)' % (self.devname.filename, self.devname.modelname))

        if not self.log:
            print('  no S.M.A.R.T attributs logged\n')
            return

        attrids = set()

        for rec in self.log:
            for attr in rec.attrs:
                attrids.add(attr)

        header = list(sorted(attrids))

        headercols = dict()
        for ixcol, attrid in enumerate(header):
            headercols[attrid] = ixcol

        # таблица строковых значений
        # первый элемент - строка, остальные - кортежи или списки из двух строк
        table = []

        nattrcols = len(header)

        # столбец ширин столбцов: timestamp и nattrcols пар столбцов значение/дельта
        colwidths = [0]
        for n in range(nattrcols):
            colwidths.append([0, 0])

        def __add_row(row):
            for ixcol, cell in enumerate(row):
                if ixcol == 0:
                    sl = len(cell)
                    if sl > colwidths[ixcol]:
                        colwidths[ixcol] = sl
                else:
                    for ixsub, s in enumerate(cell):
                        sl = len(s)
                        if sl > colwidths[ixcol][ixsub]:
                            colwidths[ixcol][ixsub] = sl

            table.append(row)

        __add_row(['Timestamp, attr(s):'] + list(map(lambda h: (str(h), 'Δ'), header)))

        def format_delta(d):
            if d == 0:
                return '—'
            else:
                vs = str(d)
                if d > 0:
                    vs = '+%s' % vs

                return vs

        for rec in self.log:
            row = [rec.timestamp.strftime(LOG_TIMEFORMAT)] + [None] * nattrcols

            for attr, vals in sorted(rec.attrs.items()):
                row[headercols[attr] + 1] = (str(vals.raw), format_delta(vals.rawdelta))

            __add_row(row)

        def format_row(row):
            t = [row[0].ljust(colwidths[0])]

            for ixcol in range(1, nattrcols + 1):
                t.append(' '.join((row[ixcol][0].rjust(colwidths[ixcol][0]), row[ixcol][1].ljust(colwidths[ixcol][1]))))

            return '  '.join(t)

        for row in table:
            print(format_row(row))

        print()

    def get_json(self):
        """Возвращает содержимое журнала в виде словаря
        для последующего вывода в формате JSON."""

        buf = []

        for rec in self.log:
            rd = rec.attrs
            buf.append((rec.timestamp.strftime(LOG_TIMEFORMAT), rd))

        return {'device':self.devname.filename, 'model':self.devname.modelname, 'log':buf}


def normalize_devmodel(devname):
    """Колхозная нормализация имени устройства вида "device_model-device_serial".
    Выяснилось, что ядро и smartd используют сходный формат, но разные разделители:
    там, где ядро ставит "-", smartd ставит "_", и наоборот.
    Поэтому пытаемся тупо все "-" заменить на "_"."""

    return devname.replace('-', '_')


def normalize_list(l):
    """Разворачивает список списков в простой список.
    Костыль для argparse..."""

    ret = []

    if l is None:
        return ret

    for sl in l:
        if isinstance(sl, list):
            ret += normalize_list(sl)
        else:
            ret.append(sl)

    return ret


MODE_SHOW, MODE_LIST = range(2)

def process_command_line():
    parser = argparse.ArgumentParser(description='This is simple smartd attributes log viewer v%s' % VERSION)

    parser.add_argument('devices', nargs='*',
        metavar='device',
        help='device name')

    parser.add_argument('--version', action='version', version=TITLE_VERSION)
    parser.add_argument('-v', '--verbose', action='count', default=0,
        help='increase verbosity level')

    pmgroupMode = parser.add_mutually_exclusive_group()
    pmgroupMode.add_argument('-s', '--show', action='store_const', const=MODE_SHOW, dest='mode',
        default=MODE_SHOW,
        help='show smartd log(s) for specified (or all) devices')
    pmgroupMode.add_argument('-l', '--list', action='store_const', const=MODE_LIST, dest='mode',
        help='display a list of connected disk devices or log files')

    parser.add_argument('-a', '--attrs', nargs='+', type=int, action='append',
        metavar='attr',
        default=[],
        help='consider only specified attributes from log files (default is %s)' % ', '.join(map(str, sorted(WATCH_ATTRS))))

    parser.add_argument('-r', '--short', action='store_const', const=True, default=False, dest='short',
        help='--show option produces shortened output (no more than %d line(s))' % MAX_LOG_RECORDS)

    parser.add_argument('-f', '--files', action='store_const', const=True, dest='readFiles',
        default=False,
        help='''if this parameter is specified, then:\n
--show counts device parameter list log file names, not device names;
--list displays a list of log files, and not a list of device names''')

    parser.add_argument('-o', '--orphans', action='store_const', const=True, dest='orphans',
        default=False,
        help='''this parameter is only valid in conjunction with the --list and --files options, otherwise ignored;
when specified, only the list is displayed those log files that do NOT match
connected disk devices''')

    pmgroupOut = parser.add_mutually_exclusive_group()
    pmgroupOut.add_argument('-t', '--text', action='store_const', dest='outputJSON', const=False, default=False,
        help='--show option produces text output (this is default behaviour)')
    pmgroupOut.add_argument('-j', '--json', action='store_const', dest='outputJSON', const=True,
        help='--show option produces JSON output')

    try:
        args = parser.parse_args()

    except Exception as ex:
        print(str(ex), file=sys.stderr)
        return 1

    if args.mode != MODE_SHOW:
        if (args.devices or args.attrs):
            parser.error('unnecessary parameters specified')
        if args.outputJSON:
            parser.error('JSON output supported by --show parameter only')

    # за каким-то [censored] argparse в случае "-arg val1 val2 -arg val3 val4"
    # хранит как [[val1, val2], [val3, val4]]
    # поэтому енту хрень надо разворачивать в плоский список
    args.devices = normalize_list(args.devices)

    return args


class DiskDevices():
    def __init__(self):
        # список устройств, содержащий экземпляры device_name:
        self.devices = []

        DEVDIR = '/dev/disk/by-id'
        for devname in os.listdir(DEVDIR):
            # интересуют только ATA и SCSI...
            md = RX_DEVNAME.match(devname)
            if md is None:
                continue

            # ...но не их разделы
            mp = RX_DEVPART.match(devname)
            if mp is not None:
                continue

            # реальное имя устройства
            devfile = os.path.split(os.path.realpath(os.path.join(DEVDIR, devname)))[1]

            self.devices.append(device_name(devfile, normalize_devmodel(md.group(2))))

    def get_by_model(self, model):
        """Возвращает экземпляр device_name по нормализованному названию
        модели model, если подходящее есть в списке, или None."""

        for devname in self.devices:
            if devname.modelname == model:
                return devname

        return None

    def print_devices(self):
        for devname in sorted(self.devices):
            print('%s: %s' % (devname.filename, devname.modelname))


def main():
    if not os.path.exists(LOG_DIR):
        print('Directory "%s" is missing. Is smartmontools installed?' % LOG_DIR, file=sys.stderr)
        return 2

    cmdargs = process_command_line()

    #
    # получаем список физически подключённых устройств
    #
    diskdevices = DiskDevices()

    #
    # получаем список файлов журналов
    #
    logfiles = []

    for fname in os.listdir(LOG_DIR):
        mf = RX_FNAME.match(fname)
        if mf is not None:
            logfiles.append(device_name(fname, normalize_devmodel(mf.group(1))))

    #
    # !!!
    #
    if cmdargs.mode == MODE_LIST:
        if cmdargs.readFiles:
            # показываем список файлов журналов
            print('Log files (in %s):' % LOG_DIR)

            for fname in logfiles:
                if cmdargs.orphans and diskdevices.get_by_model(fname.modelname):
                    continue

                print(fname.filename)
        else:
            # показываем список дисковых устройств
            print('Devices:')

            diskdevices.print_devices()

        print()

        return 0
    else:
        # cmdargs.mode == MODE_SHOW

        onlyAttrs = set(normalize_list(cmdargs.attrs))
        if not onlyAttrs:
            onlyAttrs = WATCH_ATTRS

        jsonbuf = []
        parselist = []

        if cmdargs.readFiles:
            # cmdargs.devices - имена файлов

            if not cmdargs.devices:
                # файлы не указаны - гребём всё из LOG_DIR
                for fname in logfiles:
                    cmdargs.devices.append(os.path.join(LOG_DIR, fname.filename))

            for fpath in cmdargs.devices:
                parselist.append((fpath, device_name(os.path.split(fpath)[1], 'log file')))

        else:
            # cmdargs.devices - имена устройств

            onlyDevices = set(cmdargs.devices)
            if not onlyDevices:
                onlyDevices = set(map(lambda d: d.filename, diskdevices.devices))

            for fname in logfiles:
                devname = diskdevices.get_by_model(fname.modelname)

                if not devname or not devname.filename in onlyDevices:
                    continue

                parselist.append((os.path.join(LOG_DIR, fname.filename), devname))

        for fpath, devname in parselist:
            try:
                log = SMART_Log(fpath, devname, onlyAttrs, cmdargs.short)

            except Exception as ex:
                enfo = sys.exc_info()
                em = ['error reading log file "%s": %s' % (fpath, str(ex))]

                if cmdargs.verbose > 0:
                    em += format_exception(enfo[0], enfo[1], enfo[2])

                print('\n'.join(em), file=sys.stderr)
                return 1

            if cmdargs.outputJSON:
                jsonbuf.append(log.get_json())
            else:
                log.print_table()

        if cmdargs.outputJSON:
            print(json.dumps(jsonbuf, indent='  '))

    return 0


if __name__ == '__main__':
    sys.exit(main())
