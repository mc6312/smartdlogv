#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Отладочный модуль, для работы Smartdlogv не нужен"""


import cProfile, pstats
import sys


sys.argv += ['-v', '-r', '-f', 'attrlog.sample.ata.csv']

from smartdlogv import main

with cProfile.Profile(builtins=False) as pr:
    pr.enable()
    main()
    pr.disable()
    st = pstats.Stats(pr)
    st.strip_dirs()
    st.sort_stats(pstats.SortKey.CUMULATIVE, pstats.SortKey.NFL)
    st.print_stats('smartdlogv.py:')
