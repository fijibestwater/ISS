import itertools

from django.core.paginator import EmptyPage, PageNotAnInteger
from django.http import JsonResponse

def rmerge(*args, **kwargs):
    seq_mode = kwargs.get('seq_mode', 'replace')

    if not seq_mode in ('replace', 'append', 'merge'):
        raise ValueError(
            'seq_mode must be one of "replace", "append", or "merge".')

    if len(args) < 1:
        raise TypeError('rmerge() takes at least one argument (0 given)')

    arg_types = map(type, args)
    ret_type = arg_types[0]
    homogenous = all([t == ret_type for t in arg_types])
    is_list = issubclass(ret_type, list)
    is_tuple = issubclass(ret_type, tuple)
    is_dict = issubclass(ret_type, dict)

    if not homogenous or not (is_list or is_dict or is_tuple):
        return args[-1]

    merged = ret_type()

    if (is_list or is_tuple):
        if seq_mode == 'replace':
            return args[-1]
        elif seq_mode == 'merge':
            retlen = max([len(s) for s in args])
            merged = []
            for pos_set in itertools.izip_longest(*args):
                pos_set = [x for x in pos_set if x != None]
                pos = rmerge(*pos_set, seq_mode=seq_mode)
                merged.append(pos)
            return ret_type(merged)
        elif seq_mode == 'append':
            for arg in args:
                merged += arg
            return merged

    else:
        for arg in args:
            for key in arg:
                if key in merged:
                    merged[key] = rmerge(merged[key], arg[key])
                else:
                    merged[key] = arg[key]

        return merged

def render_mixed_mode(request, templates, additional={}):
    data = {}

    for key_name, template, ctx in templates:
        markup = render(request, template, ctx).content
        data[key_name] = markup

    data.update(additional)

    return JsonResponse(data)


__all__ = [
    'rmerge',
    'render_mixed_mode',
]
