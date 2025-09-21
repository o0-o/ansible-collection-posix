# vim: ts=4:sw=4:sts=4:et:ft=python
# -*- mode: python; tab-width: 4; indent-tabs-mode: nil; -*-
#
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
#
# Copyright (c) 2025 oØ.o (@o0-o)
#
# This file is part of the o0_o.posix Ansible Collection.

"""Exception helpers for unit tests."""

from __future__ import annotations

from typing import Any, Callable, Type, Union

ExcArg = Union[BaseException, Type[BaseException]]


def boom(exc: ExcArg = ValueError, msg: str = "boom") -> Callable[..., None]:
    """Return a callable that raises the given exception when invoked.

    :param exc: Exception instance or type to raise
    :param msg: Message when an exception type is provided
    :returns: Callable that raises the exception on call
    """

    def _raise(*args: Any, **kwargs: Any) -> None:
        if isinstance(exc, BaseException):
            raise exc
        raise exc(msg)

    return _raise
