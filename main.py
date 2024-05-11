import tkinter as tk
from tkinter import ttk, filedialog
from pytube import YouTube
from tkinter import messagebox

def load_streams():
    url = url_entry.get()
    try:
        yt = YouTube(url)
        stream_list.delete(0, tk.END)
        stream_dict.clear()

        if video_check.get():  # Si l'utilisateur souhaite les flux vidéo
            video_streams = yt.streams.filter(progressive=True, file_extension='mp4')
            for stream in video_streams:
                stream_info = f"Video {stream.itag} - {stream.resolution} - {stream.mime_type}"
                stream_list.insert(tk.END, stream_info)
                stream_dict[stream_info] = stream

        if audio_check.get():  # Si l'utilisateur souhaite les flux audio
            audio_streams = yt.streams.filter(only_audio=True)
            for stream in audio_streams:
                stream_info = f"Audio {stream.itag} - {stream.abr} - {stream.mime_type}"
                stream_list.insert(tk.END, stream_info)
                stream_dict[stream_info] = stream

    except Exception as e:
        messagebox.showerror("Erreur", str(e))

def download_stream():
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

style = ttk.Style()
style.theme_use('clam')

tk.Label(app, text="URL de la vidéo:").pack(pady=10)
url_entry = ttk.Entry(app, width=50)
url_entry.pack(pady=10)

# Cases à cocher pour les options de téléchargement
video_check = tk.BooleanVar()
video_check.set(True)  # Par défaut, coché
audio_check = tk.BooleanVar()
audio_check.set(True)  # Par défaut, coché
ttk.Checkbutton(app, text="Flux vidéo", variable=video_check).pack()
ttk.Checkbutton(app, text="Flux audio", variable=audio_check).pack()

load_button = ttk.Button(app, text="Charger les flux", command=load_streams)
load_button.pack(pady=10)

tk.Label(app, text="Choisir le format de flux:").pack()
stream_list = tk.Listbox(app, width=50)
stream_list.pack(pady=10)

download_button = ttk.Button(app, text="Télécharger le flux", command=download_stream)
download_button.pack(pady=10)

stream_dict = {}

app.mainloop()
