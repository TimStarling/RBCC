import importlib


def test_all_application_modules_import_without_audio_hardware_or_gui_root():
    modules = [
        "config",
        "models",
        "noise_analyzer",
        "frequency_selector",
        "alarm_generator",
        "audio_input",
        "result_exporter",
        "main_cli",
        "main_gui",
    ]
    for module in modules:
        importlib.import_module(module)
