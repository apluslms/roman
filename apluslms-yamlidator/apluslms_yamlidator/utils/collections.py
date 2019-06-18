import sys
from abc import ABCMeta
from collections.abc import (
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)


if sys.version_info >= (3, 7) or sys.version_info >= (3, 6) and sys.implementation.name == 'cpython':
    # The dictionary implementation in cPython 3.6 keeps order and starting from 3.7 it's in the standard.
    # Defining the OrderedDict as a dict here keeps representations etc. a bit more clear
    OrderedDict = dict
    # NOTE: dict does not implement .poptiem() or .move_to_end()
else:
    from collections import OrderedDict


class OrderedDefaultDict(OrderedDict):
    __slots__ = ('default_factory',)

    def __init__(self, default_factory, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value


# Special method __init_subclass__ can be used for this starting from Python 3.6
# TODO: reimplement with __init_subclass__ after support for <3.6 is dropped
class ChangesMeta(ABCMeta):
    def __new__(metacls, name, bases, namespace, wraps=None, **kwargs):
        cls = super().__new__(metacls, name, bases, namespace)
        if wraps is not None:
            for w in wraps:
                cls._registry[w] = cls
        return cls

    def __init__(cls, name, bases, namespace, **kwargs):
        return super().__init__(name, bases, namespace)


class Changes(metaclass=ChangesMeta):
    _registry = {}

    @classmethod
    def get_wrapper(cls, data):
        for w, c in cls._registry.items():
            if isinstance(data, w):
                return c
        return None

    @classmethod
    def wrap(cls, data, *, parent=None, key=None, default=None):
        wrapper = cls.get_wrapper(data)
        if wrapper:
            return wrapper(data, parent=parent, key=key, default=default)
        return data

    def __init__(self, data, *, parent=None, key=None, **kwargs):
        super().__init__()
        self._data = data
        self._parent = parent
        self._key = key

    def _on_update(self):
        if self._parent:
            self._parent.data_updated(self._key, self._data)

    def data_updated(self, key, data):
        self._on_update()

    def get_data(self):
        return self._data


class ChangesList(Changes, MutableSequence, wraps=(MutableSequence, list)):
    def __init__(self, data=None, *, parent=None, key=None, default=None):
        super().__init__([], parent=parent, key=key)
        if data is not None:
            for item in data:
                self._data.append(self.wrap(item, parent=self))

    def __iter__(self):
        yield from self._data

    def __len__(self):
        return len(self._data)

    def __contains__(self, value):
        return any(val == value for val in self._data)

    def __getitem__(self, idx):
        return self._data[idx]

    def __setitem__(self, idx, value):
        self._data[idx] = self.wrap(value, parent=self)
        self._on_update()

    def __delitem__(self, idx):
        del self._data[idx]
        self._on_update()

    def insert(self, idx, value):
        self._data.insert(idx, self.wrap(value, parent=self))
        self._on_update()

    def get_data(self):
        return [
            value.get_data() if isinstance(value, Changes) else value
            for value in self._data
        ]


class ChangesDict(Changes, MutableMapping, wraps=(MutableMapping, dict)):
    def __init__(self, data=None, *, parent=None, key=None, default=None):
        if data is None:
            data = {}
        super().__init__(data, parent=parent, key=key)
        self._defaults = {}
        self._work = OrderedDict()
        self.updatework(data)
        if default is not None:
            self.setdefaults(default)

    def __iter__(self):
        yield from self._work

    def __len__(self):
        return len(self._work)

    def __contains__(self, key):
        return key in self._work

    def __getitem__(self, key):
        return self._work[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self._work[key] = self.wrap(value, parent=self, key=key, default=self._defaults.get(key))
        self._on_update()

    def __delitem__(self, key):
        del self._work[key]
        self._data.pop(key, None)
        self._on_update()

    def setwork(self, key, value):
        wrapper = self.get_wrapper(value)
        if wrapper:
            value = self.wrap(value, parent=self, key=key, default=self._defaults.get(key))
        self._work[key] = value

    def updatework(self, data):
        if isinstance(data, (Mapping, dict)):
            data = data.items()
        for key, value in data:
            self.setwork(key, value)

    def setdefault(self, key, value):
        self._defaults.setdefault(key, value)
        if key not in self._work:
            self._work[key] = self.wrap(value, parent=self, key=key, default=self._defaults.get(key))
        return self._work[key]

    def setdefaults(self, data):
        if isinstance(data, Mapping):
            data = data.items()
        for key, value in data:
            self.setdefault(key, value)

    def data_updated(self, key, data):
        if data:
            self._data[key] = data
        else:
            self._data.pop(key, None)
        super().data_updated(key, data)

    def __repr__(self):
        data = OrderedDict()
        defaults = OrderedDict()
        for k, v in self._work.items():
            if k in self._data:
                data[k] = v
            else:
                defaults[k] = v
        return "{}(data={}, default={})".format(
            self.__class__.__name__,
            repr(data),
            repr(defaults),
        )
