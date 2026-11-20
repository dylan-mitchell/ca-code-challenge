"""Use Vite's development server or its production manifest from Django."""

import json
from pathlib import Path

from django import template
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

register = template.Library()


def _dev_url():
    return getattr(settings, "VITE_DEV_SERVER_URL", "").rstrip("/")


def _manifest():
    path = Path(settings.FRONTEND_DIST) / "manifest.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ImproperlyConfigured(
            "Frontend assets are missing. Run npm ci && npm run build in frontend, "
            "or set VITE_DEV_SERVER_URL while running npm run dev."
        ) from exc


def _entry(manifest, name):
    try:
        return manifest[name]
    except KeyError as exc:
        raise ImproperlyConfigured(f"Vite manifest is missing {name!r}; rebuild frontend assets.") from exc


def _dependencies(manifest, name, seen=None):
    seen = seen if seen is not None else set()
    if name in seen:
        return []
    seen.add(name)
    entry = _entry(manifest, name)
    return [entry] + [
        dependency
        for imported in entry.get("imports", [])
        for dependency in _dependencies(manifest, imported, seen)
    ]


def _css_tags(context, paths):
    seen = context.render_context.setdefault("vite_css_paths", set())
    fresh = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            fresh.append((path,))
    return format_html_join("\n", '<link rel="stylesheet" href="{}">', fresh)


@register.simple_tag(takes_context=True)
def vite_css(context, name):
    if dev := _dev_url():
        return _css_tags(context, [f"{dev}/{name}?direct"])
    dependencies = _dependencies(_manifest(), name)
    paths = [
        static(f"frontend/{path}")
        for entry in dependencies
        for path in ([entry["file"]] if entry["file"].endswith(".css") else []) + entry.get("css", [])
    ]
    return _css_tags(context, paths)


@register.simple_tag
def vite_dev_client():
    if dev := _dev_url():
        return format_html('<script type="module" src="{}/@vite/client"></script>', dev)
    return ""


@register.simple_tag(takes_context=True)
def vite_js(context, name):
    if dev := _dev_url():
        # React's official backend integration needs this preamble before its entry.
        return format_html(
            '<script type="module">'
            'import RefreshRuntime from "{}/@react-refresh";'
            'RefreshRuntime.injectIntoGlobalHook(window);'
            'window.$RefreshReg$ = () => {{}};'
            'window.$RefreshSig$ = () => (type) => type;'
            'window.__vite_plugin_react_preamble_installed__ = true;'
            '</script>\n<script type="module" src="{}/{}"></script>',
            dev, dev, name,
        )
    manifest = _manifest()
    dependencies = _dependencies(manifest, name)
    styles = vite_css(context, name)
    preloads = format_html_join(
        "\n", '<link rel="modulepreload" href="{}">',
        ((static(f"frontend/{item['file']}"),) for item in dependencies[1:] if item["file"].endswith(".js")),
    )
    return format_html('{}\n{}\n<script type="module" src="{}"></script>', styles, preloads, static(f"frontend/{dependencies[0]['file']}"))
