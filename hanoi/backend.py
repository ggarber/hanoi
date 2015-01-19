import zlib

try:
    from redis import Redis
except ImportError:
    # Redis not available
    pass


class Feature(object):

    __slots__ = ['name', 'function', 'percentage', 'enabled']

    def __init__(self, name, function, percentage):
        if not isinstance(name, basestring):
            raise AttributeError("Feature name should be a string")

        self.name = name
        self.function = function
        self.percentage = self._validate_percentage(percentage)
        self.enabled = True

    def _validate_percentage(self, percentage):
        try:
            value = int(percentage)
        except ValueError:
            raise AttributeError("Percentage should be a valid number")

        if 0 > value or value > 100:
            raise AttributeError("Percentage should be a number between 0 and 100")
        return value

    def get_item_id(self, item):
        return self.function(item) if self.function else str(item)

    def __setattr__(self, name, value):
        """
        Validate two fields while setting them:
        - percentage should be an integeger between 0 and 100
        - name is read only
        """
        if name == 'percentage':
            value = self._validate_percentage(value)
        elif name == 'name' and hasattr(self, name):
            raise RuntimeError("Unable to update the Feature name")

        object.__setattr__(self, name, value)

    def __repr__(self):
        return "<{0}> applying {1} to {2}% users".format(
            self.name,
            self.function,
            self.percentage
        )


class MemoryBackEnd(object):

    def __init__(self):
        self.funcs = {}
        self.reg = {}
        self.rules = {}

    def get_functionalities(self):
        return self.funcs.keys()

    def add_functionality(self, fn):
        self.funcs[fn.name] = fn

    def get_functionality(self, name):
        return self.funcs[name]

    def _add(self, name, item):
        self.reg[name].append(item)

    def add(self, name, item):
        if not name in self.reg:
            self.reg[name] = []

        if isinstance(item, basestring):
            self._add(name, item)
        elif self.funcs[name].function:
            self._add(name, self.funcs[name].function(item))
        else:
            self._add(name, item)

    def set_rule(self, name, rule):
        self.rules[name] = rule

    def set_percentage(self, name, percentage):
        self.funcs[name].percentage = percentage

    def is_enabled(self, name, item=None):
        func_is_enabled = name in self.funcs and self.funcs[name].enabled
        if item is None:
            # Global funcionality enabled?
            return func_is_enabled

        if not func_is_enabled:
            # Avoid additional lookup as the functionality is globally disabled
            return func_is_enabled

        flag = self.funcs[name].percentage == 100
        flag = flag or (name in self.reg and item in self.reg[name])
        flag = flag or (name in self.rules and self.rules[name].search(str(item)) is not None)
        if not flag and self.funcs[name].percentage > 0:
            flag = zlib.crc32(self.funcs[name].get_item_id(item)) % 100 >= self.funcs[name].percentage
        return flag

    def disable(self, name):
        self.funcs[name].enabled = False

    def enable(self, name, enable_to_all=False):
        self.funcs[name].enabled = True
        if enable_to_all:
            self.funcs[name].percentage = 100

    def toggle(self, name):
        self.funcs[name].enabled = not self.funcs[name].enabled


class RedisBackEnd(object):

    PREFIX = "rollout:{0}"

    def __init__(self, obj):
        if isinstance(obj, (list, tuple)):
            host, port = obj[0], obj[1]
            db = obj[2] if len(obj) >= 3 else 0
            self._redis = Redis(host=host, port=port, db=db)
        else:
            self._redis = obj

        self._prefix_len = len(self.PREFIX.format(''))
        self.rules = {}

    @classmethod
    def unserialize_feature(cls, name, value):
        if value:
            enabled, percentage, users = value.split("|")
        else:
            percentage = 100
            users = None
            enabled = '1'

        f = Feature(name, None, percentage)
        f.enabled = enabled == '1'

        return f, users.split(",") if users else []

    def _get_func_key(self, name):
        return self.PREFIX.format(name)

    def get_functionalities(self):
        func = self._redis.keys(self._get_func_key('*'))  # HACK: get every functionality
        return map(lambda x: x[self._prefix_len:], func)

    def add_functionality(self, fn, users=None):
        data = ",".join(users) if users is not None else ''
        self._redis.set(
            self._get_func_key(fn.name),
            "|".join(['1' if fn.enabled else '0', str(fn.percentage), data])
        )

    def get_functionality(self, name):
        redis_value = self._redis.get(self._get_func_key(name))
        return self.unserialize_feature(name, redis_value)

    def _add(self, name, item):
        func, users = self.get_functionality(name)
        if item not in users:
            users.append(item)
            self.add_functionality(func, users)
        else:
            pass  # Avoid duplicating users

    def add(self, name, item):
        if isinstance(item, basestring):
            self._add(name, item)
        elif self.funcs[name].function:
            self._add(name, self.funcs[name].function(item))
        else:
            self._add(name, item)

    def set_rule(self, name, rule):
        self.rules[name] = rule

    def set_percentage(self, name, percentage):
        func, users = self.get_functionality(name)
        func.percentage = percentage
        self.add_functionality(func, users)

    def is_enabled(self, name, item=None):
        func_is_enabled = name in self.get_functionalities()
        functionality, users = self.get_functionality(name)
        func_is_enabled = func_is_enabled and functionality.enabled

        if item is None:
            # Global funcionality enabled?
            return func_is_enabled

        if not func_is_enabled:
            # Avoid additional lookup as the functionality is globally disabled
            return func_is_enabled

        flag = functionality.percentage == 100
        flag = flag or (name in users)
        flag = flag or (name in self.rules and self.rules[name].search(str(item)) is not None)
        if not flag and functionality.percentage > 0:
            flag = zlib.crc32(item) % 100 >= functionality.percentage
        return flag

    def disable(self, name):
        func, users = self.get_functionality(name)
        func.enabled = False
        self.add_functionality(func, users)

    def enable(self, name, enable_to_all=False):
        func, users = self.get_functionality(name)
        func.enabled = True
        if enable_to_all:
            func.percentage = 100
        self.add_functionality(func, users)

    def toggle(self, name):
        func, users = self.get_functionality(name)
        func.enabled = not func.enabled
        self.add_functionality(func, users)