import tkinter as tk
from tkinter import filedialog
from pytube import YouTube
from tkinter import messagebox


def load_video():
    url = url_entry.get()
    try:
        yt = YouTube(url)
        streams = yt.streams.filter(progressive=True)
        stream_list.delete(0, tk.END)
        stream_dict.clear()
        for stream in streams:
            stream_info = f"{stream.itag} - {stream.mime_type} - {stream.resolution}"
            stream_list.insert(tk.END, stream_info)
            stream_dict[stream_info] = stream
    except Exception as e:
        messagebox.showerror("Erreur", str(e))


def download_video():
    selection = stream_list.curselection()
    if not selection:
        messagebox.showerror("Erreur", "Veuillez sélectionner un format")
        return
    stream_info = stream_list.get(selection[0])
    stream = stream_dict[stream_info]
    save_path = filedialog.askdirectory()
    if save_path:
        stream.download(save_path)
        messagebox.showinfo("Succès", "Téléchargement terminé")


app = tk.Tk()
app.title("Téléchargeur YouTube")

tk.Label(app, text="URL de la vidéo:").pack()
url_entry = tk.Entry(app, width=50)
url_entry.pack()

load_button = tk.Button(app, text="Charger vidéo", command=load_video)
load_button.pack()

tk.Label(app, text="Choisir le format de flux:").pack()
stream_list = tk.Listbox(app, width=50)
stream_list.pack()

download_button = tk.Button(app, text="Télécharger vidéo", command=download_video)
download_button.pack()

stream_dict = {}  # Dictionnaire pour stocker les références des flux

app.mainloop()
