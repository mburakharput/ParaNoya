import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from bank_logo_renderer import bank_icon, menu_icon
from ailefinans import App

class BankVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_symbol_logo_is_fully_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'symbol.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><symbol id="logo" viewBox="-50 -10 100 20"><rect x="-50" y="-10" width="40" height="20" fill="red"/><rect x="10" y="-10" width="40" height="20" fill="blue"/></symbol><use href="#logo" x="-50" y="-10" width="100" height="20" transform="translate(50 10)"/></svg>')
            image = bank_icon(path).pixmap(QSize(96,24),1).toImage()
            self.assertGreater(image.pixelColor(10,12).red(), 200)
            self.assertGreater(image.pixelColor(85,12).blue(), 200)

    def test_clipped_wordmark_does_not_become_solid_rectangle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sekerbank.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><defs><clipPath id="clip"><path d="M0 0 L100 20 L0 20 Z"/></clipPath></defs><g clip-path="url(#clip)"><rect width="100" height="20" fill="green"/></g></svg>')
            image = bank_icon(path).pixmap(QSize(96,24),1).toImage()
            self.assertEqual(image.pixelColor(85,5).alpha(), 0)
            self.assertGreater(image.pixelColor(10,18).alpha(), 200)

    def test_menu_gutter_is_transparent_at_high_dpi(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'logo.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><rect width="100" height="20" fill="red"/></svg>')
            image = menu_icon(path).pixmap(QSize(110,24),3).toImage()
            self.assertEqual(image.width(),330)
            self.assertTrue(all(image.pixelColor(x,y).alpha()==0
                                for x in range(288,330) for y in range(72)))

    def test_logo_bounds_are_stable_across_display_scaling(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'wide.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 30"><rect width="1000" height="30" fill="red"/></svg>')
            for density in (1,1.5,2,3):
                pix=menu_icon(path).pixmap(QSize(110,24),density)
                self.assertLessEqual(pix.width()/pix.devicePixelRatio(),110)
                self.assertLessEqual(pix.height()/pix.devicePixelRatio(),24)
                self.assertFalse(pix.isNull())

    def test_mascot_image_is_circular_with_white_rim(self):
        from ailefinans import circular_mascot
        image=circular_mascot(Path(__file__).parent/'assets'/'paranoya_mascot.png').toImage()
        self.assertEqual(image.pixelColor(0,0).alpha(),0)
        self.assertEqual(image.pixelColor(image.width()-1,0).alpha(),0)
        self.assertEqual(image.pixelColor(image.width()//2,4).name(),'#ffffff')
        self.assertGreater(image.pixelColor(image.width()//2,image.height()//2).alpha(),200)

    def test_missing_logo_detail_uses_fixed_size_fallback(self):
        from PySide6.QtWidgets import QLabel
        host=SimpleNamespace(_bank_icon=lambda name: App._bank_icon(None,name),devicePixelRatioF=lambda:2)
        label=QLabel()
        App._set_detail_logo(host,label,'Bilinmeyen Banka')
        self.assertEqual(label.size(),QSize(110,34))
        self.assertFalse(label.hasScaledContents())
        self.assertFalse(label.isHidden())

    def test_bank_metadata_resolves_custom_nicknames_without_guessing(self):
        db=sqlite3.connect(':memory:')
        try:
            db.executescript("""
                CREATE TABLE accounts(id INTEGER, name TEXT, profile_id INTEGER);
                CREATE TABLE account_bank_details(account_id INTEGER,bank_name TEXT);
                CREATE TABLE credit_cards(id INTEGER,name TEXT,profile_id INTEGER);
                CREATE TABLE card_catalog_links(card_id INTEGER,bank TEXT);
                INSERT INTO accounts VALUES(1,'Maaşım',1),(2,'Ortak',1),(3,'Ortak',1);
                INSERT INTO account_bank_details VALUES(1,'Enpara Bank'),(2,'Akbank'),(3,'Şekerbank');
                INSERT INTO credit_cards VALUES(9,'Market kartım',1);
                INSERT INTO card_catalog_links VALUES(9,'Şekerbank');
            """)
            host=SimpleNamespace(db=db,pid=lambda:1)
            host._bank_aliases=App._build_bank_aliases(host)
            self.assertEqual(App._bank_for_text(host,'Maaşım (1.000 TL)'),'Enpara Bank')
            self.assertEqual(App._bank_for_text(host,'Market kartım'),'Şekerbank')
            self.assertEqual(App._bank_for_text(host,'Ortak'),'')
            self.assertEqual(App._bank_for_text(host,'Bilinmiyor'),'')
        finally:
            db.close()

    def test_bank_menus_keep_item_data_and_consistent_logo_spacing(self):
        from PySide6.QtWidgets import QWidget, QComboBox, QTableWidget
        from PySide6.QtGui import QIcon
        host=SimpleNamespace(_bank_aliases={'Maaşım': {'Enpara Bank'},'Şekerbank': {'Şekerbank'}})
        host._bank_for_text=lambda text: App._bank_for_text(host,text)
        host._bank_icon=lambda name: QIcon()
        root=QWidget()
        account=QComboBox(root)
        account.addItem('Maaşım (1.000 TL)',17)
        card=QComboBox(root)
        card.addItem('Şekerbank — Kart',('Şekerbank','Kart'))
        App._decorate_bank_widgets(host,root)
        self.assertEqual(account.itemData(0),17)
        self.assertEqual(card.itemData(0),('Şekerbank','Kart'))
        for combo in (account,card):
            self.assertEqual(combo.iconSize(),QSize(110,24))
            self.assertEqual(combo.maximumWidth(),420)
            self.assertEqual(combo.maxVisibleItems(),5)
        table=QTableWidget(0,1)
        table.setHorizontalHeaderLabels(['Hesap'])
        App.fill_table(host,table,[('Maaşım',)])
        self.assertEqual(table.item(0,0).text(),'Maaşım')
        self.assertEqual(table.iconSize(),QSize(110,24))
