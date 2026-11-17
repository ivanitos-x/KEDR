from ..contracts import RasterData,Asset,AssetFailure

class QtRasterLoader:
    def probe(self,header): return header.startswith(b'\x89PNG\r\n\x1a\n')
    def load(self,path,context):
        from PySide6.QtGui import QImageReader,QImage
        context.check()
        reader=QImageReader(str(path)); size=reader.size()
        if size.width()<=0 or size.width()*size.height()>40_000_000:
            raise AssetFailure('invalid_input','CLAP-VIEW-002','Лимит — 40 миллионов пикселей')
        image=reader.read()
        if image.isNull(): raise AssetFailure('invalid_input','CLAP-VIEW-002',reader.errorString())
        alpha=image.hasAlphaChannel()
        image=image.convertToFormat(QImage.Format.Format_RGBA8888)
        data=RasterData(bytes(image.constBits()),image.width(),image.height(),alpha)
        return Asset(data,frozenset({'view.move','view.zoom'}),{'width':data.width,'height':data.height,'alpha':alpha})
