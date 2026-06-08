"""Resolve patchable settings from the pipeline facade module."""


def get_attr(name):
    from app.services.cidr import cidr_list_updater, pipeline_facade

    if hasattr(pipeline_facade, name):
        return getattr(pipeline_facade, name)
    return getattr(cidr_list_updater, name)


def call(name, *args, **kwargs):
    return get_attr(name)(*args, **kwargs)
