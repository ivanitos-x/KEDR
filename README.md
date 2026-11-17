# KEDR

Автономный просмотрщик изображений, тайлов Build Engine и 3D-моделей для Windows. Открывает PNG, ART, KVX, MD2, MD3, GLB и статические BLEND. Для 3D используется OpenGL.

## Установка в Windows x64

Скачайте установщик из [GitHub Releases](https://github.com/ivanitos-x/KEDR/releases/latest) и запустите его. Python и Qt входят в поставку. KEDR появится в меню «Пуск» и в «Открыть с помощью» для KVX, MD2, MD3, GLB и BLEND. PNG и ART можно открыть внутри KEDR.

## Сборка и запуск из исходников

Нужен Python 3.11 или новее. В PowerShell выполните `.\setup.ps1`, затем запустите `KEDR.exe`. Скрипт создаёт локальное окружение Python и собирает EXE-лаунчер. Для запуска через Python можно использовать `KEDR.cmd`. Ассоциации Windows добавляются через `register-associations.cmd`.

```powershell
.\KEDR.exe "model.glb"
.\KEDR.exe --mode=pbr "model.blend"
.\KEDR.exe --palette "PALETTE.DAT" "TILES000.ART"
.\KEDR.exe --grp "DUKE3D.GRP" --entry-index 395
```

Индекс GRP начинается с нуля и соответствует записи в каталоге выбранного архива.

## Управление

Первый щелчок по фоновому окну активирует его. Короткий щелчок левой кнопкой по активному окну закрывает его. Средняя кнопка перемещает окно, колесо меняет масштаб, а правая кнопка открывает меню. Перетаскивание левой кнопкой вращает 3D-модель. В сетке ART двойной щелчок открывает тайл, а стрелки переключают соседние ART.

## Возможности

- ART открывается отдельно или прямо из GRP, с анимацией Build и экспортом прозрачного PNG. Путь внешней палитры сохраняется для архива или папки.
- KVX сразу отображается во встроенных цветах, с возможностью выбрать внешнюю палитру Build VGA или режим Solid. MD2 и MD3 показывают первый кадр и ищут рядом PNG, JPG или JPEG.
- GLB показывает статические треугольники и базовые параметры материалов. BLEND читается без Blender и поддерживает часть материалов и Subdivision Surface.
- Контекстное меню моделей предлагает Solid, «Материалы», PBR и автоматическое вращение. В PBR можно загрузить локальное Radiance HDRI.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe tests/render_glb_check.py
```

## Сборка установщика

После `setup.ps1` установите Inno Setup 6 и выполните:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-installer.ps1 -Version 1.0.0
```

Установщик появится в папке `release`. Если Inno Setup установлен в другом месте, укажите путь к `ISCC.exe` через `-Iscc`.
