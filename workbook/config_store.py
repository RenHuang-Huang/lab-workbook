"""Portable configuration: mutable user files are never part of an update ZIP."""
import copy
import datetime as dt
import json
import os
import tempfile
from pathlib import Path

SYSTEM_KEYS = ('database_path', 'output_directory', 'order_mode', 'merge_workno_style')
PRINT_DIR = 'print_settings'
PRINT_FILES = ('settings.json', 'layout_settings.json', 'catalog.json')
# Bump when normalization/migration semantics change independently of APP_VERSION.
NORMALIZATION_VERSION = 1


def read(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('設定檔必須是 JSON 物件；原檔已保留。')
    return value


def print_only(settings):
    return {k: copy.deepcopy(v) for k, v in settings.items() if k not in (*SYSTEM_KEYS, 'layout')}


def system_defaults(root):
    return dict(database_path='', output_directory=str(Path(root) / 'output'),
                order_mode='merge', merge_workno_style='first')


def system_values(value, root):
    result = system_defaults(root)
    for key in SYSTEM_KEYS:
        if key in value:
            if not isinstance(value[key], str):
                raise ValueError('系統設定欄位格式不正確。')
            result[key] = value[key]
    if result['order_mode'] not in ('split', 'merge') or result['merge_workno_style'] not in ('first', 'all'):
        raise ValueError('拆單／併單模式設定不正確。')
    return result


def transaction(targets):
    """Stage every JSON before replacing; restore original bytes on I/O failure."""
    staged, committed = [], []
    try:
        for target, value in targets:
            target = Path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            before = target.read_bytes() if target.exists() else None
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                             suffix='.tmp', delete=False) as stream:
                staged.append((target, Path(stream.name), before))
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        for target, temp, before in staged:
            os.replace(temp, target)
            committed.append((target, before))
    except Exception:
        for target, before in reversed(committed):
            if before is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(before)
        raise
    finally:
        for _, temp, _ in staged:
            temp.unlink(missing_ok=True)


def normalize(settings, layout, catalog=None):
    from . import core, layout_settings as ls, catalog_cache as cc
    from . import source_panels, subregions, catalog_settings, font_settings, print_style
    result = core.default_settings()
    result.update(print_only(settings))  # Only missing options get new defaults, never reset user values.
    result['font_sizes'] = font_settings.sizes(result)
    print_style.validate_settings(result)
    layout = copy.deepcopy(layout)
    config = cc.overrides(result, layout)
    if catalog is not None:
        if not isinstance(catalog.get('raw_catalog'), dict):
            raise ValueError('JSON 字典格式不正確；請使用完整舊版程式資料夾。')
        raw = cc.clean(catalog['raw_catalog'])
        # Only reuse a fully migrated, current and intact projection. Changed
        # settings/dictionary, damaged projections and upgrades take the full path.
        if (catalog.get('normalization_version') == NORMALIZATION_VERSION
                and catalog.get('schema_version') == cc.SCHEMA_VERSION
                and catalog.get('app_version') == cc.APP_VERSION
                and catalog.get('catalog_fingerprint') == cc.fingerprint(raw)
                and catalog.get('settings_fingerprint') == cc.fingerprint(config)
                and catalog.get('settings') == config
                and isinstance(catalog.get('records'), list)
                and isinstance(catalog.get('lists'), dict)
                and catalog.get('projection_fingerprint') == cc.fingerprint([catalog['records'], catalog['lists']])):
            return result, layout, catalog
        usable, _ = cc.display_catalog(raw)
        layout, _ = source_panels.transfer(layout, usable)
        layout = subregions.migrate(layout, catalog_settings.records(usable, result, layout))
        layout = subregions.apply_bio_groups(layout, catalog_settings.records(usable, result, layout))
        catalog = cc.build(catalog['raw_catalog'], result, layout, catalog.get('source', {}))
        catalog['normalization_version'] = NORMALIZATION_VERSION
    else:
        # Without a dictionary, leave evidence-dependent migrations to the existing editor.
        ls.validate(layout)
    return result, layout, catalog


def read_bundle(root, *, allow_defaults=False):
    """Read one explicit application folder; never search AppData or other versions."""
    root = Path(root)
    folders = [root / PRINT_DIR, root / 'workbook']
    if allow_defaults:
        folders.append(root / 'defaults' / PRINT_DIR)
    folder = next((p for p in folders if (p / 'settings.json').exists()), None)
    if folder is None:
        if allow_defaults and not any((root / folder / name).exists()
                                      for folder in (PRINT_DIR, 'workbook', 'defaults/print_settings')
                                      for name in PRINT_FILES):
            # Public releases contain code defaults only, never a developer's saved settings.
            from . import core, layout_settings as ls
            settings, layout, catalog = normalize(core.default_settings(), ls.defaults())
            preferences = root / 'preferences.json'
            system = system_values(read(preferences), root) if preferences.exists() else None
            return dict(settings=settings, layout=layout, catalog=catalog, system=system,
                        system_present=system is not None)
        raise ValueError('找不到列印設定，請選擇含工作簿輸出.exe 的舊版資料夾。')
    if not (folder / 'layout_settings.json').is_file():
        raise ValueError('缺少 layout_settings.json，未帶入不完整的列印設定。')
    raw_settings = read(folder / 'settings.json')
    catalog = (read(folder / 'catalog.json') or None) if (folder / 'catalog.json').exists() else None
    settings, layout, catalog = normalize(raw_settings, read(folder / 'layout_settings.json'), catalog)
    preferences = root / 'preferences.json'
    if not preferences.exists() and allow_defaults and folder == root / 'defaults' / PRINT_DIR:
        preferences = root / 'defaults' / 'system_seed.json'
    system = system_values(read(preferences), root) if preferences.exists() else None
    return dict(settings=settings, layout=layout, catalog=catalog, system=system,
                system_present=system is not None)


def targets(root, bundle, include_system=True):
    root = Path(root)
    result = [(root / PRINT_DIR / 'settings.json', print_only(bundle['settings'])),
              (root / PRINT_DIR / 'layout_settings.json', bundle['layout'])]
    # An empty cache invalidates an unrelated destination dictionary if the source has none.
    result.append((root / PRINT_DIR / 'catalog.json', bundle['catalog'] or {}))
    if include_system and bundle.get('system') is not None:
        result.append((root / 'preferences.json', bundle['system']))
    return result


def backup(root, files):
    root = Path(root)
    folder = root / 'config_backups' / dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for path in files:
        path = Path(path)
        if path.is_file():
            dest = folder / path.relative_to(root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    return folder


def ensure_configuration(root):
    """Same-folder upgrade: existing user files win over all packaged defaults."""
    root = Path(root)
    current = root / PRINT_DIR / 'settings.json'
    bundle = read_bundle(root, allow_defaults=True)
    changes = []
    for target, value in targets(root, bundle, include_system=False):
        # Comparing canonical objects avoids rewriting the dictionary on every startup.
        if not target.exists() or read(target) != value:
            changes.append((target, value))
    if not (root / 'preferences.json').exists():
        changes.append((root / 'preferences.json', bundle['system'] or system_defaults(root)))
    if changes:
        originals = [p for p, _ in changes]
        if not current.exists():
            originals += [root / 'workbook' / n for n in PRINT_FILES]
        backup(root, originals)
        transaction(changes)
    return bundle


def import_previous(source, destination, include_system=True):
    """Explicit transfer, with destination backup and validation before any write."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('請選擇另一個舊版程式資料夾。')
    bundle = read_bundle(source)
    writes = targets(destination, bundle, include_system)
    saved = backup(destination, [p for p, _ in writes])
    transaction(writes)
    return dict(bundle=bundle, backup=saved,
                system_imported=include_system and bundle['system_present'])


def export_backup(root, destination):
    bundle = read_bundle(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    transaction(targets(destination, bundle))
    return destination
