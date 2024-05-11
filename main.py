import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox,
                             QListWidget, QFileDialog, QMessageBox)
from pytube import YouTube


class YouTubeDownloader(QWidget):
    """
    Main window of the application

    Attributes:
        load_button (QPushButton): Button to load streams
        stream_list (QListWidget): List of available streams
        download_button (QPushButton): Button to download selected stream
        audio_check (QCheckBox): Checkbox to select audio streams
        video_check (QCheckBox): Checkbox to select video streams
        url_entry (QLineEdit): Entry to input the video URL
        stream_dict (dict): Dictionary to store stream information
    """
    def __init__(self):
        super().__init__()
        self.load_button = None
        self.stream_list = None
        self.download_button = None
        self.audio_check = None
        self.video_check = None
        self.url_entry = None
        self.stream_dict = None
        self.init_ui()

    def init_ui(self):
        # Layout principal
        layout = QVBoxLayout()

        # URL Entry
        url_layout = QHBoxLayout()
        self.url_entry = QLineEdit(self)
        url_layout.addWidget(QLabel("URL de la vidéo:"))
        url_layout.addWidget(self.url_entry)
        layout.addLayout(url_layout)

        # Checkboxes for video and audio streams
        self.video_check = QCheckBox("Flux vidéo", self)
        self.video_check.setChecked(True)
        self.audio_check = QCheckBox("Flux audio", self)
        self.audio_check.setChecked(True)
        layout.addWidget(self.video_check)
        layout.addWidget(self.audio_check)

        # Button to load streams
        self.load_button = QPushButton("Load streams", self)
        self.load_button.clicked.connect(self.load_streams)
        layout.addWidget(self.load_button)

        # ListWidget to display available streams
        self.stream_list = QListWidget(self)
        layout.addWidget(self.stream_list)

        # Button to download selected stream
        self.download_button = QPushButton("Download flux", self)
        self.download_button.clicked.connect(self.download_stream)
        layout.addWidget(self.download_button)

        # Set layout
        self.setLayout(layout)
        self.setWindowTitle("Youtube Downloader")
        self.setGeometry(300, 300, 600, 400)

    def load_streams(self):
        url = self.url_entry.text()
        try:
            yt = YouTube(url)
            self.stream_list.clear()
            self.stream_dict = {}

            if self.video_check.isChecked():
                video_streams = yt.streams.filter(progressive=True, file_extension='mp4')
                for stream in video_streams:
                    stream_info = f"Video {stream.itag} - {stream.resolution} - {stream.mime_type}"
                    self.stream_list.addItem(stream_info)
                    self.stream_dict[stream_info] = stream

            if self.audio_check.isChecked():
                audio_streams = yt.streams.filter(only_audio=True)
                for stream in audio_streams:
                    stream_info = f"Audio {stream.itag} - {stream.abr} - {stream.mime_type}"
                    self.stream_list.addItem(stream_info)
                    self.stream_dict[stream_info] = stream

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def download_stream(self):
        stream_info = self.stream_list.currentItem().text()
        if stream_info:
            stream = self.stream_dict[stream_info]
            save_path = QFileDialog.getExistingDirectory(self, "Select Directory")
            if save_path:
                stream.download(save_path)
                QMessageBox.information(self, "Success", "Download completed")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = YouTubeDownloader()
    ex.show()
    sys.exit(app.exec_())
