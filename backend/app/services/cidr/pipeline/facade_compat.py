"""Resolve patchable settings from the pipeline facade module."""


def get_attr(name):
    from app.services.cidr import pipeline_facade

    return getattr(pipeline_facade, name)


def call(name, *args, **kwargs):
    return get_attr(name)(*args, **kwargs)
