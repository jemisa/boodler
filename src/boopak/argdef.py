import sys
import types

# We use "type" as an argument and local variable sometimes, but we need
# to keep track of the standard type() function.
_typeof = type

class ArgList:
	"""ArgList: represents the argument structure of a function. This
	includes the number of arguments, their names, and their types.

	Actually, arguments can be specified by position *or* by name,
	although both is more common. The ArgList can also specify
	extra positional arguments -- describing the f(*ls) Python
	syntax. (It cannot currently describe the f(**dic) syntax.)

	Constructor:
	
		ArgList(...) -- constructor

	You can construct the ArgList with positional arguments:

		ArgList(Arg(...), Arg(...), ...)

	...or with named arguments:

		ArgList(x=Arg(...), y=Arg(...), ...)

	The former is equivalent to specifying the index= value in the Arg
	constructor; the latter, the name= value.

	You can also include an ArgExtra object in the arguments:

		ArgList(ArgExtra(...))

	This defines the type of extra positional arguments. Note that the
	ArgExtra must be included before any named arguments.

	Static methods:

	from_argspec() -- construct an ArgList from a Python function
	merge() -- construct an ArgList by merging two ArgLists
	from_node() -- construct an ArgList from an S-expression

	Internal methods:

	sort_args() -- finish constructing the ArgList
	
	Public methods:

	get_index() -- return the Arg with the given index number
	get_name() -- return the Arg with the given name
	clone() -- construct an ArgList identical to this one
	to_node() -- construct an S-expression from this ArgList
	dump() -- print out the ArgList
	max_accepted() -- return the maximum number of positional arguments
	min_accepted() -- return the minimum number of positional arguments
	resolve() -- match a Tree of argument values against the ArgList
	"""
	
	def __init__(self, *ls, **dic):
		self.args = []
		self.listtype = None
		
		pos = 1
		for arg in ls:
			if (isinstance(arg, ArgExtra)):
				self.listtype = arg.type
				continue
			if (not isinstance(arg, Arg)):
				raise ArgDefError('ArgList argument must be Arg')
			if (arg.index is None):
				arg.index = pos
			pos += 1
			self.args.append(arg)
			
		for key in dic.keys():
			arg = dic[key]
			if (not isinstance(arg, Arg)):
				raise ArgDefError('ArgList argument must be Arg')
			if (arg.name is None):
				arg.name = key
			else:
				if (arg.name != key):
					raise ArgDefError('argument name does not match: ' + key + ', ' + arg.name)
			self.args.append(arg)

		self.sort_args()

	def sort_args(self):
		"""sort_args() -> None

		Finish constructing the ArgList. This puts the arguments in a
		consistent order. It raises ArgDefError if there are any
		inconsistencies (like two arguments with the same name).

		This is an internal method. It should only be called by methods
		that construct ArgLists.
		"""
		
		self.args.sort(_argument_sort_func)
		for arg in self.args:
			if (arg.index is None):
				continue
			ls = [ arg2 for arg2 in self.args if arg2.index == arg.index ]
			if (len(ls) > 1):
				raise ArgDefError('more than one argument with index ' + str(arg.index))
		for arg in self.args:
			if (arg.name is None):
				continue
			ls = [ arg2 for arg2 in self.args if arg2.name == arg.name ]
			if (len(ls) > 1):
				raise ArgDefError('more than one argument with name ' + str(arg.name))

	def __repr__(self):
		ls = [ (arg.name or '...') for arg in self.args ]
		return '<ArgList (' + (', '.join(ls)) + ')>'

	def __len__(self):
		return len(self.args)

	def __nonzero__(self):
		return True

	def get_index(self, val):
		"""get_index(val) -> Arg

		Return the Arg with the given index number. If there isn't one,
		returns None.
		"""
		
		for arg in self.args:
			if ((not (arg.index is None)) and (arg.index == val)):
				return arg
		return None

	def get_name(self, val):
		"""get_index(val) -> Arg

		Return the Arg with the given name. If there isn't one,
		returns None.
		"""
		
		for arg in self.args:
			if ((not (arg.name is None)) and (arg.name == val)):
				return arg
		return None

	def clone(self):
		"""clone() -> ArgList

		Construct an ArgList identical to this one.
		"""
		
		arglist = ArgList()
		arglist.listtype = self.listtype
		for arg in self.args:
			arglist.args.append(arg.clone())
		# Don't need to sort, because self is already sorted.
		return arglist

	def to_node(self):
		"""to_node() -> Tree

		Construct an S-expression from this ArgList.
		"""
		
		nod = sparse.List(sparse.ID('arglist'))
		ls = [ arg.to_node() for arg in self.args ]
		nod.append(sparse.List(*ls))
		if (self.listtype):
			nod.set_attr('listtype', type_to_node(self.listtype))
		return nod

	def dump(self, fl=sys.stdout):
		"""dump(fl=sys.stdout) -> None

		Print out the ArgList to stdout, or another stream. This method
		prints in a human-readable form; it is intended for debugging.
		"""
		
		fl.write('ArgList:\n')
		for arg in self.args:
			fl.write('  Arg:\n')
			if (not (arg.index is None)):
				val = ''
				if (arg.optional):
					val = ' (optional)'
				fl.write('    index: ' + str(arg.index) + val + '\n')
			if (not (arg.name is None)):
				fl.write('    name: ' + arg.name + '\n')
			if (arg.hasdefault):
				fl.write('    default: ' + repr(arg.default) + '\n')
			if (not (arg.type is None)):
				fl.write('    type: ' + repr(arg.type) + '\n')
		if (self.listtype):
			fl.write('  *Args: ' + repr(self.listtype) + '\n')

	def max_accepted(self):
		"""max_accepted() -> int

		Return the maximum number of positional arguments accepted by
		the ArgList. If it accepts extra positional arguments, this
		returns None.
		"""
		
		if (self.listtype):
			return None
		return len(self.args)
		
	def min_accepted(self):
		"""min_accepted() -> int

		Return the minimum number of positional arguments accepted by
		the ArgList.
		"""
		
		ls = [ arg for arg in self.args if (not arg.optional) ]
		return len(ls)

	def from_argspec(args, varargs, varkw, defaults):
		"""from_argspec(args, varargs, varkw, defaults) -> ArgList

		Construct an ArgList from a Python function. The four arguments
		are those returned by inspect.getargspec() -- see the inspect module
		in the Python standard library.

		This uses the names and positions of the function arguments
		to define an ArgList. If an argument has a default value, its
		value and type are used as well.

		If the function has extra positional arguments -- f(*ls) --
		they are taken to be an arbitrary number of untyped arguments.
		
		If the function has extra named arguments -- f(**dic) --
		then ArgDefError is raised.
		"""
		
		if (varkw):
			raise ArgDefError('cannot understand **' + varkw)
		arglist = ArgList()

		if (varargs):
			arglist.listtype = list

		if (defaults is None):
			defstart = len(args)
		else:
			defstart = len(args) - len(defaults)
		
		pos = 1
		for key in args[1:]:
			dic = {}
			if (pos >= defstart):
				val = defaults[pos-defstart]
				dic['default'] = val
				if (not (val is None)):
					dic['type'] = infer_type(val)
			arg = Arg(name=key, index=pos, **dic)
			pos += 1
			arglist.args.append(arg)
			
		arglist.sort_args()
		return arglist
	from_argspec = staticmethod(from_argspec)

	def merge(arglist1, arglist2=None):
		"""merge(arglist1, arglist2=None) -> ArgList

		Construct an ArgList by merging two ArgLists. This does not
		modify the arguments; it creates a new ArgList.

		The merge algorithm is somewhat ad-hoc. It is intended for a
		particular purpose: merging the _args ArgList of an Agent
		class with the from_argspec() ArgList.

		If the second list is None, this returns (a clone of) the first list.

		Otherwise, each argument in the second list is considered. If it
		exists in the first list (same index or name), their characteristics
		are merged. If not, the argument is appended to the first list.

		When arguments are merged, the characteristics in the first list
		take precedence -- except for the optional flag, which is always
		taken from the second list. (It makes sense, honest.)
		"""
		
		arglist = arglist1.clone()
		if (arglist2 is None):
			return arglist

		unmerged = []
		for arg2 in arglist2.args:
			arg = None
			if (not (arg2.index is None)):
				arg = arglist.get_index(arg2.index)
			if ((arg is None) and not (arg2.name is None)):
				arg = arglist.get_name(arg2.name)
			if (arg is None):
				unmerged.append(arg2)
			else:
				arg.absorb(arg2)
		for arg in unmerged:
			arglist.args.append(arg)
		arglist.sort_args()
		return arglist
	merge = staticmethod(merge)
	
	def resolve(self, node):
		"""resolve(node) -> (list, dict)

		Match a Tree of argument values against the ArgList. Convert each
		value to the appropriate type, fill in any necessary default
		values, and return the values needed to call the function that
		the ArgList represents.

		The Tree must be a List with at least one (positional) value.
		This first value is ignored -- it is assumed to be the name
		of the function that this ArgList came from.

		Raises ArgDefError if the arguments fail to match in any way.
		(Too few, too many, can't be converted to the right type...)
		
		The return values are a list and dict, such as you might expect
		to use in the form f(*ls, **dic). However, you wouldn't actually
		do that, because the contents of the list and dict are wrapped
		values. (See the ArgWrapper class.) You could use the resolve()
		function this way:

			(ls, dic) = arglist.resolve(tree)
			wrap = ArgClassWrapper(f, ls, dic)
			wrap()
		"""
		
		if (not isinstance(node, sparse.List)):
			raise ArgDefError('arguments must be a list')
		if (len(node) == 0):
			raise ArgDefError('arguments must contain a class name')
		
		valls = node[ 1 : ]
		valdic = node.attrs

		posmap = {}
		pos = 0
		for arg in self.args:
			if (not (arg.index is None)):
				posmap[arg.index] = pos
			if (not (arg.name is None)):
				posmap[arg.name] = pos
			pos += 1

		filled = [ False for arg in self.args ]
		values = [ None for arg in self.args ]
		extraindexed = []
		extranamed = {}

		index = 1
		for valnod in valls:
			pos = posmap.get(index)
			if (pos is None):
				extraindexed.append(valnod)
				index += 1
				continue
			arg = self.args[pos]
			if (filled[pos]):
				raise ArgDefError('multiple values for indexed argument ' + str(index))
			filled[pos] = True
			values[pos] = node_to_value(arg.type, valnod)
			index += 1

		for key in valdic:
			valnod = valdic[key]
			pos = posmap.get(key)
			if (pos is None):
				extranamed[key] = valnod
				continue
			arg = self.args[pos]
			if (filled[pos]):
				raise ArgDefError('multiple values for named argument ' + key)
			filled[pos] = True
			values[pos] = node_to_value(arg.type, valnod)

		pos = 0
		for arg in self.args:
			if (not filled[pos] and not arg.optional):
				if (arg.hasdefault):
					filled[pos] = True
					values[pos] = arg.default
				else:
					raise ArgDefError(str(self.min_accepted()) + ' arguments required')
			pos += 1

		if (extranamed):
			raise ArgDefError('unknown named argument: ' + (', '.join(extranamed.keys())))

		resultls = []
		resultdic = {}

		indexonly = 0
		pos = 0
		for arg in self.args:
			if (arg.name is None and filled[pos]):
				indexonly = pos+1
			pos += 1

		pos = 0
		for arg in self.args:
			if (filled[pos]):
				if (pos < indexonly):
					resultls.append(values[pos])
				else:
					resultdic[arg.name] = values[pos]
			pos += 1

		if (not self.listtype):
			if (extraindexed):
				raise ArgDefError('at most ' + str(self.max_accepted()) + ' arguments accepted')
		else:
			exls = node_to_seq_value(self.listtype, extraindexed)
			if (isinstance(exls, ArgListWrapper)
				or isinstance(exls, ArgTupleWrapper)):
				# unwrap just the top list, so that we can iterate on it here
				exls = exls.ls
			for val in exls:
				resultls.append(val)
				
		# extranamed are not currently supported

		return (resultls, resultdic)
		
	def from_node(node):
		"""from_node(node) -> ArgList

		Construct an ArgList from an S-expression. The Tree passed in should
		be one generated by the to_node() method.
		"""
		
		if (not isinstance(node, sparse.List) or len(node) < 1
			or not isinstance(node[0], sparse.ID)
			or node[0].as_string() != 'arglist'):
			raise ArgDefError('must be an (arglist) list')
		if (len(node) != 2 or not isinstance(node[1], sparse.List)):
			raise ArgDefError('second element must be a list of types')

		res = ArgList()
		for val in node[1]:
			res.args.append(Arg.from_node(val))
		if (node.has_attr('listtype')):
			res.listtype = node_to_type(node.get_attr('listtype'))
		return res
	from_node = staticmethod(from_node)
	
def _argument_sort_func(arg1, arg2):
	"""_argument_sort_func(arg1, arg2) -> int

	Sort comparison function, used by ArgList.sort_args(). This sorts
	arguments by their index value. Arguments with no index are sorted
	last.
	"""
	
	ix1 = arg1.index
	ix2 = arg2.index
	if (ix1 is None and ix2 is None):
		return 0
	if (ix1 is None):
		return 1
	if (ix2 is None):
		return -1
	return cmp(ix1, ix2)
	
_DummyDefault = object()
	
class Arg:
	###
		
	def __init__(self, name=None, index=None,
		type=None, default=_DummyDefault, optional=None,
		description=None):

		if (name is None):
			self.name = None
		else:
			if (not (_typeof(name) in [str, unicode])):
				raise ArgDefError('name must be a string; was ' + repr(name))
			self.name = name
			
		if (not (index is None) and index <= 0):
			raise ArgDefError('index must be positive; was ' + str(index))
		self.index = index
		
		self.type = type
		self.optional = optional
		if (default is _DummyDefault):
			self.hasdefault = False
			self.default = None
		else:
			self.hasdefault = True
			self.default = default
			if ((self.type is None) and not (default is None)):
				self.type = infer_type(default)
		check_valid_type(self.type)
		if (self.optional is None):
			self.optional = self.hasdefault
		else:
			self.optional = bool(self.optional)
		self.description = description

	def __repr__(self):
		val = '<Arg'
		if (not (self.index is None)):
			val += ' ' + str(self.index)
		if (not (self.name is None)):
			val += " '" + self.name + "'"
		val += '>'
		return val
	
	def clone(self):
		if (self.hasdefault):
			default = self.default
		else:
			default = _DummyDefault
		arg = Arg(name=self.name, index=self.index,
			type=self.type, default=default, optional=self.optional,
			description=self.description)
		return arg

	def to_node(self):
		nod = sparse.List(sparse.ID('arg'))
		if (not (self.name is None)):
			nod.set_attr('name', sparse.ID(self.name))
		if (not (self.index is None)):
			nod.set_attr('index', value_to_node(int, self.index))
		if (not (self.description is None)):
			nod.set_attr('description', sparse.ID(self.description))
		if (not (self.optional is None)):
			if (self.optional != self.hasdefault):
				nod.set_attr('optional', value_to_node(bool, self.optional))
		if (not (self.type is None)):
			nod.set_attr('type', type_to_node(self.type))
		if (self.hasdefault):
			nod.set_attr('default', value_to_node(self.type, self.default))
		return nod

	def absorb(self, arg):
		attrlist = ['name', 'index']
		for key in attrlist:
			val = getattr(arg, key)
			if (val is None):
				continue
			sval = getattr(self, key)
			if (sval is None):
				setattr(self, key, val)
				continue
			if (val != sval):
				raise ArgDefError('argument ' + key + ' does not match: ' + str(val) + ', ' + str(sval))
			
		attrlist = ['type', 'description']
		for key in attrlist:
			val = getattr(arg, key)
			if (val is None):
				continue
			sval = getattr(self, key)
			if (sval is None):
				setattr(self, key, val)
				continue
			# No warning if these attrs don't match
			
		if (arg.hasdefault):
			if (not self.hasdefault):
				self.hasdefault = True
				self.default = arg.default
			# No warning if defaults don't match

		self.optional = arg.optional
		# Always absorb the optional attribute

	def from_node(node):
		if (not isinstance(node, sparse.List) or len(node) != 1
			or not isinstance(node[0], sparse.ID)
			or node[0].as_string() != 'arg'):
			raise ArgDefError('must be an (arg) list')
		dic = {}
		if (node.has_attr('name')):
			dic['name'] = node.get_attr('name').as_string()
		if (node.has_attr('index')):
			dic['index'] = node.get_attr('index').as_integer()
		if (node.has_attr('description')):
			dic['description'] = node.get_attr('description').as_string()
		if (node.has_attr('optional')):
			dic['optional'] = node.get_attr('optional').as_boolean()
		if (node.has_attr('type')):
			dic['type'] = node_to_type(node.get_attr('type'))
		if (node.has_attr('default')):
			wrap = node_to_value(dic.get('type'), node.get_attr('default'))
			dic['default'] = instantiate(wrap)
			### What if this is an AgentClass?
			### should this *always* be a wrapped value? For the cases where
			### the default is an Agent instance that we don't know how to
			### construct. (That would break unserialization, I guess.)
			### (but maybe the default value is being instantiated already!)
		return Arg(**dic)
	from_node = staticmethod(from_node)
	
class ArgExtra:
	def __init__(self, type=list):
		if (not (type in [list, tuple]
			or isinstance(type, ListOf)
			or isinstance(type, TupleOf))):
			raise ArgDefError('ArgExtra must be a list, tuple, ListOf, or TupleOf: was ' + str(type))
		self.type = type
		
class ArgDefError(ValueError):
	"""ArgDefError: represents an error constructing an ArgList.
	"""
	pass

class SequenceOf:
	classname = None
	def __init__(self, *types, **opts):
		if (not self.classname):
			raise Exception('you cannot instantiate SequenceOf directly; use ListOf or TupleOf')
		if (not types):
			notypes = True
			types = ( None, )
		else:
			notypes = False
		self.types = types
		for typ in self.types:
			check_valid_type(typ)
		if (not opts):
			self.default_setup(notypes)
		else:
			self.min = opts.pop('min', 0)
			self.max = opts.pop('max', None)
			self.repeat = opts.pop('repeat', len(self.types))
			if (opts):
				raise ArgDefError(self.classname + ' got unknown keyword argument: ' + (', '.join(opts.keys())))
		if (self.min < 0):
			raise ArgDefError(self.classname + ' min is negative')
		if (not (self.max is None)):
			if (self.max < self.min):
				raise ArgDefError(self.classname + ' max is less than min')
		if (self.repeat > len(self.types)):
			raise ArgDefError(self.classname + ' repeat is greater than number of types')
		if (self.repeat <= 0):
			raise ArgDefError(self.classname + ' repeat is less than one')
			
	def __repr__(self):
		ls = [ repr(val) for val in self.types ]
		if (self.repeat < len(self.types)):
			ls.insert(len(self.types) - self.repeat, '...')
			ls.append('...')
		res = (', '.join(ls))
		if (self.min == 0 and self.max is None):
			pass
		elif (self.max is None):
			res = str(self.min) + ' or more: ' + res
		elif (self.min == self.max):
			res = 'exactly ' + str(self.min) + ': ' + res
		else:
			res = str(self.min) + ' to ' + str(self.max) + ': ' + res
		return '<' + self.classname + ' ' + res + '>'

	def to_node(self):
		nod = sparse.List(sparse.ID(self.classname))
		ls = [ type_to_node(val) for val in self.types ]
		nod.append(sparse.List(*ls))
		nod.set_attr('min', value_to_node(int, self.min))
		if (not (self.max is None)):
			nod.set_attr('max', value_to_node(int, self.max))
		if (self.repeat != len(self.types)):
			nod.set_attr('repeat', value_to_node(int, self.repeat))
		return nod

class ListOf(SequenceOf):
	classname = 'ListOf'
	def default_setup(self, notypes):
		self.min = 0
		self.max = None
		self.repeat = len(self.types)

class TupleOf(SequenceOf):
	classname = 'TupleOf'
	def default_setup(self, notypes):
		if (notypes):
			self.min = 0
			self.max = None
		else:
			self.min = len(self.types)
			self.max = len(self.types)
		self.repeat = len(self.types)

class Wrapped:
	def __init__(self, type):
		check_valid_type(type)
		if (isinstance(type, Wrapped)):
			raise ArgDefError('cannot put Wrapped in a Wrapped')
		self.type = type
		
def infer_type(val):
	type = _typeof(val)
	
	if (type == types.InstanceType):
		if (isinstance(val, pinfo.File)):
			return sample.Sample
		if (isinstance(val, sample.Sample)):
			return sample.Sample
		return val.__class__
	
	if (type == types.ClassType):
		return Wrapped(val)
	
	return type

_type_to_name_mapping = {
	None: 'none',
	str: 'str', unicode: 'str',
	int: 'int', long: 'int',
	float: 'float',
	bool: 'bool',
	list: 'list',
	tuple: 'tuple',
}

_name_to_type_mapping = {
	'none': None,
	'str': str,
	'int': int,
	'float': float,
	'bool': bool,
	'list': list,
	'tuple': tuple,
}

def check_valid_type(type):
	if (_type_to_name_mapping.has_key(type)):
		return
	if (isinstance(type, ListOf) or isinstance(type, TupleOf)):
		return
	if (_typeof(type) == types.ClassType):
		if (issubclass(type, sample.Sample)):
			return
		if (issubclass(type, Agent)):
			return
	if (isinstance(type, Wrapped)):
		return
	raise ArgDefError('unrecognized type: ' + str(type))

def type_to_node(type):
	if (_type_to_name_mapping.has_key(type)):
		name = _type_to_name_mapping[type]
		return sparse.ID(name)
	if (isinstance(type, ListOf) or isinstance(type, TupleOf)):
		return type.to_node()
	if (_typeof(type) == types.ClassType):
		if (issubclass(type, sample.Sample)):
			return sparse.ID('Sample')
		if (issubclass(type, Agent)):
			return sparse.ID('Agent')
	if (isinstance(type, Wrapped)):
		nod = type_to_node(type.type)
		return sparse.List(sparse.ID('Wrapped'), nod)
	raise ArgDefError('type_to_node: unrecognized type: ' + str(type))

def node_to_type(nod):
	if (isinstance(nod, sparse.ID)):
		id = nod.as_string()
		if (_name_to_type_mapping.has_key(id)):
			return _name_to_type_mapping[id]
		if (id == 'Sample'):
			return sample.Sample
		if (id == 'Agent'):
			return Agent
		raise ArgDefError('node_to_type: unrecognized type: ' + id)

	# the node is a List

	if (len(nod) < 1 or (not isinstance(nod[0], sparse.ID))):
		raise ArgDefError('type list must begin with an ID')
	id = nod[0].as_string()
	
	if (id in [ListOf.classname, TupleOf.classname]):
		if (len(nod) != 2 or (not isinstance(nod[1], sparse.List))):
			raise ArgDefError(id + ' must be followed by one list')
		if (id == ListOf.classname):
			cla = ListOf
		else:
			cla = TupleOf
		ls = [ node_to_type(val) for val in nod[1] ]
		dic = {}
		val = nod.get_attr('min')
		if (val):
			dic['min'] = val.as_integer()
		val = nod.get_attr('max')
		if (val):
			dic['max'] = val.as_integer()
		val = nod.get_attr('repeat')
		if (val):
			dic['repeat'] = val.as_integer()
		return cla(*ls, **dic)

	if (id == 'Wrapped'):
		if (len(nod) != 2):
			raise ArgDefError('Wrapped must be followed by one type')
		return Wrapped(node_to_type(nod[1]))
	
	raise ArgDefError('node_to_type: unrecognized type: ' + id)

def value_to_node(type, val):
	if (val is None):
		return sparse.List(no=sparse.ID('value'))
	
	if (isinstance(type, Wrapped)):
		return value_to_node(type.type, val)
	
	if (type is None):
		if (_typeof(val) in [list, tuple]):
			type = list
		else:
			type = str
	
	if (type in [str, unicode]):
		if (_typeof(val) in [str, unicode]):
			return sparse.ID(val)
		else:
			return sparse.ID(str(val))
	if (type in [int, long, float]):
		return sparse.ID(str(val))
	if (type == bool):
		val = str(bool(val)).lower()
		return sparse.ID(val)
	if (type in [list, tuple]
		or isinstance(type, ListOf)
		or isinstance(type, TupleOf)):
		return seq_value_to_node(type, val)
	
	if (_typeof(type) == types.ClassType and issubclass(type, sample.Sample)):
		loader = pload.PackageLoader.global_loader
		if (not loader):
			raise ArgDefError('cannot locate resource, because there is no loader')
		(pkg, resource) = loader.find_item_resources(val)
		### it might be necessary to figure out what versionspec the
		### module used to load this object's package, and include
		### it along with pkg.name!
		return sparse.ID(pkg.name + '/' + resource.key)

	if (_typeof(type) == types.ClassType and issubclass(type, Agent)):
		loader = pload.PackageLoader.global_loader
		if (not loader):
			raise ArgDefError('cannot locate resource, because there is no loader')
		cla = val
		if (_typeof(cla) == types.InstanceType):
			cla = cla.__class__
		(pkg, resource) = loader.find_item_resources(cla)
		### it might be necessary to figure out what versionspec the
		### module used to load this object's package, and include
		### it along with pkg.name!
		return sparse.ID(pkg.name + '/' + resource.key)

	raise ArgDefError('value_to_node: unrecognized type: ' + str(type))

def seq_value_to_node(type, vallist):
	if (type == list):
		type = ListOf()
	elif (type == tuple):
		type = TupleOf()
		
	typelist = type.types
	ls = sparse.List()
	pos = 0
	for val in vallist:
		nod = value_to_node(typelist[pos], val)
		ls.append(nod)
		pos += 1
		if (pos >= len(typelist)):
			pos = len(typelist) - type.repeat

	return ls

def node_to_value(type, node):
	### would be nice if this took an argument-label argument
	
	if (isinstance(node, sparse.List) and len(node) == 0):
		subnod = node.get_attr('no')
		if (subnod and isinstance(subnod, sparse.ID)
			and subnod.as_string() == 'value'):
			return None
	
	if (isinstance(type, Wrapped)):
		val = node_to_value(type.type, node)
		if (isinstance(val, ArgWrapper)):
			val.keep_wrapped = True
		return val
	
	if (type is None):
		if (isinstance(node, sparse.ID)):
			type = str
		else:
			type = list
		
	if (type in [str, unicode]):
		return node.as_string()
	if (type in [int, long]):
		return node.as_integer()
	if (type == float):
		return node.as_float()
	if (type == bool):
		return node.as_boolean()
	if (type in [list, tuple]
		or isinstance(type, ListOf)
		or isinstance(type, TupleOf)):
		if (not isinstance(node, sparse.List)):
			raise ValueError('argument must be a list')
		if (node.attrs):
			raise ValueError('list argument may not have attributes')
		return node_to_seq_value(type, node.list)
	
	if (_typeof(type) == types.ClassType and issubclass(type, sample.Sample)):
		loader = pload.PackageLoader.global_loader
		if (not loader):
			raise ArgDefError('cannot load resource, because there is no loader')
		return loader.load_item_by_name(node.as_string())
	
	if (_typeof(type) == types.ClassType and issubclass(type, Agent)):
		loader = pload.PackageLoader.global_loader
		if (not loader):
			raise ArgDefError('cannot load resource, because there is no loader')
		#cla = loader.load_item_by_name(node.as_string())
		#return cla()
		wrap = load_described(loader, node)
		return wrap

	raise ValueError('cannot handle type: ' + str(type))

def node_to_seq_value(type, nodelist):
	if (type == list):
		type = ListOf()
	elif (type == tuple):
		type = TupleOf()
		
	if isinstance(type, ListOf):
		wrapper = ArgListWrapper
	elif isinstance(type, TupleOf):
		wrapper = ArgTupleWrapper
	else:
		raise ValueError('cannot handle type: ' + str(type))

	typelist = type.types

	if (type.min == type.max and len(nodelist) != type.min):
		raise ValueError('exactly ' + str(type.min) + ' elements required: ' + str(len(nodelist)) + ' found')
	if (len(nodelist) < type.min):
		raise ValueError('at least ' + str(type.min) + ' elements required: ' + str(len(nodelist)) + ' found')
	if (not (type.max is None)):
		if (len(nodelist) > type.max):
			raise ValueError('at most ' + str(type.max) + ' elements required: ' + str(len(nodelist)) + ' found')
	
	ls = []
	pos = 0
	for valnod in nodelist:
		val = node_to_value(typelist[pos], valnod)
		ls.append(val)
		pos += 1
		if (pos >= len(typelist)):
			pos = len(typelist) - type.repeat
			
	return wrapper.create(ls)

class ArgWrapper:
	keep_wrapped = False
	def unwrap(self):
		raise Exception('unwrap() is not implemented for ' + repr(self))

class ArgClassWrapper(ArgWrapper):
	def create(cla, ls, dic=None):
		ls = list(ls)
		return ArgClassWrapper(ls, dic)
	create = staticmethod(create)

	def __init__(self, cla, ls, dic=None):
		self.cla = cla
		self.argls = ls
		self.argdic = dic
	def __call__(self):
		return self.unwrap()
	def unwrap(self):
		ls = [ instantiate(val) for val in self.argls ]
		if (not self.argdic):
			print '### ArgClassWrapper:', self.cla, 'with', ls
			return self.cla(*ls)
		dic = dict([ (key,instantiate(val)) for (key,val) in self.argdic.items() ])
		print '### ArgClassWrapper:', self.cla, 'with', ls, dic
		return self.cla(*ls, **dic)

class ArgListWrapper(ArgWrapper):
	def create(ls):
		ls = list(ls)
		return ArgListWrapper(ls)
	create = staticmethod(create)
	
	def __init__(self, ls):
		self.ls = ls
	def unwrap(self):
		return [ instantiate(val) for val in self.ls ]

class ArgTupleWrapper(ArgWrapper):
	def create(tup):
		tup = tuple(tup)
		muts = [ val for val in tup if isinstance(val, ArgWrapper) ]
		if (not muts):
			return tup
		return ArgTupleWrapper(tup)
	create = staticmethod(create)
	
	def __init__(self, tup):
		self.tup = tup
	def unwrap(self):
		ls = [ instantiate(val) for val in self.tup ]
		return tuple(ls)

	
def instantiate(val):
	if (isinstance(val, ArgWrapper)):
		if (not val.keep_wrapped):
			return val.unwrap()
	return val

# Late imports.

from boodle import sample
from boopak import sparse, pinfo, pload

# from boodle.agent import Agent, load_described
#
# These definitions are actually done by the boodle.agent module, when it
# imports this one. If you import this module alone, it will suffer from
# "... is not defined" errors. Hopefully this won't be a problem in
# practice.
