#!/usr/bin/env python
# coding: utf-8
"""English-language entry point for Jable SmallTool."""

from locales import set_lang
set_lang('en')

from jable_smalltool import main
main()
