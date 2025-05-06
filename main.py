import threading
import queue
import azure.cognitiveservices.speech as speechsdk
import uuid
import time
import requests
import tkinter as tk
from tkinter import scrolledtext
import os


# === Setup Queues ===
audio_queue = queue.Queue()
text_queue = queue.Queue()
text_queue_for_gui = queue.Queue()
text_queue_interim = queue.Queue()
translated_text_queue = queue.Queue()

# Tambahkan daftar kata yang ingin dikecualikan dan custom translasi
# Kata-kata yang tidak akan diterjemahkan
excluded_words = ["Azure", "Good morning"]
# Daftar kata yang ingin dikecualikan dan custom translasi
custom_translations = {
    "hello": "salam",
    "Hello": "salam",
    "orange": "jeruk bali",
    "Orange": "jeruk bali",
}  # Kata-kata dengan arti khusus


# Tambahkan flag global untuk menghentikan thread
stop_flag = False
threads = []

language_code = "en-US"  # Ganti ke "id-ID" kalau Bahasa Indonesia

# Tambahkan konfigurasi Azure Speech SDK
# Pastikan key disimpan di environment variable
speech_key = os.getenv("AZURE_SPEECH_KEY")
service_region = "southeastasia"  # Ganti dengan region Azure Anda


def exclude_words(sentence):
    """Mengecualikan kata-kata tertentu dengan membungkusnya dalam tanda kurung."""
    for word in excluded_words:
        sentence = sentence.replace(word, "-".join(word))
    return sentence


def restore_excluded_words(translated_text):
    """Mengembalikan kata-kata yang dikecualikan ke bentuk aslinya."""
    for word in excluded_words:
        translated_text = translated_text.replace("-".join(word), word)
    return translated_text


def mark_custom_words(sentence):
    """Tandai kata-kata tertentu dengan placeholder sebelum translasi."""
    for word in custom_translations.keys():
        sentence = sentence.replace(word, "*".join(word))
    return sentence


def replace_marked_words(translated_text):
    """Ganti placeholder dengan arti khusus setelah translasi."""
    for word, replacement in custom_translations.items():
        translated_text = translated_text.replace(
            "*".join(word), replacement)
    return translated_text


def transcribe_from_microphone():
    """Merekam audio dari mikrofon dan mengirimkannya ke Azure Speech-to-Text."""
    try:
        text_queue_for_gui.put(
            "================= ▶️ started =====================")
        text_queue_interim.put(
            "================= ▶️ started =====================")

        # Konfigurasi Azure Speech SDK
        speech_config = speechsdk.SpeechConfig(
            subscription=speech_key, region=service_region)
        speech_config.speech_recognition_language = language_code

        # Gunakan mikrofon sebagai input audio
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)

        # Buat recognizer
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config)

        def handle_final_result(evt):
            """Callback untuk hasil transkripsi final."""
            transcript = evt.result.text
            text_queue.put(transcript)
            text_queue_interim.put(transcript)
            text_queue_for_gui.put(transcript)
            text_queue_for_gui.put("-----------------------------------------")
            print(f"Hasil Transkripsi (Final): {transcript}")

        def handle_interim_result(evt):
            """Callback untuk hasil transkripsi interim."""
            transcript = evt.result.text
            print(f"Hasil Transkripsi (Interim): {transcript}")
            text_queue_interim.put(transcript)

        # Sambungkan event handler
        speech_recognizer.recognized.connect(handle_final_result)
        speech_recognizer.recognizing.connect(handle_interim_result)

        # Mulai pengenalan suara
        print("🎤 [Azure] Start listening...")
        speech_recognizer.start_continuous_recognition()

        while not stop_flag:
            time.sleep(0.5)  # Tunggu hingga stop_flag diubah

        # Hentikan pengenalan suara
        speech_recognizer.stop_continuous_recognition()
        print("🎤 [Azure] Stop listening...")

    except Exception as e:
        print(f"Error Transkripsi: {e}")
        import traceback
        traceback.print_exc()  # Menampilkan stack trace untuk analisis lebih lanjut

    text_queue_for_gui.put("================= ⏹️ stopped ====================")
    text_queue_interim.put("================= ⏹️ stopped ====================")


# ==== GUI Tkinter ====


class TextDisplayGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Live Preprocessed and Translated Text")

        # Tombol kontrol
        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=10)

        self.play_button = tk.Button(
            self.button_frame, text="Play", command=self.start_processes, font=("Arial", 12))
        self.play_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = tk.Button(
            self.button_frame, text="Stop", command=self.stop_processes, font=("Arial", 12))
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(
            self.button_frame, text="Clear", command=self.clear_text, font=("Arial", 12))
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # Panel atas untuk teks interim
        self.text_area_interim = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, width=80, height=4, font=("Arial", 15), bg="#ADFFF5")
        self.text_area_interim.pack(padx=10, pady=5)

        # Panel atas untuk teks dari split_text_queue
        self.text_area_original = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, width=80, height=12, font=("Arial", 15))
        self.text_area_original.pack(padx=10, pady=5)

        # Panel bawah untuk teks dari translated_text_queue
        self.text_area_translated = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, width=80, height=12, font=("Arial", 15))
        self.text_area_translated.tag_configure(
            "translated_text", foreground="#007A37", font=("Arial", 15, "bold"))
        self.text_area_translated.pack(padx=10, pady=5)

        # Jalankan fungsi update UI secara berkala
        self.update_ui()

    def start_processes(self):
        global threads, stop_flag
        stop_flag = False
        if not threads:  # Cegah memulai ulang thread yang sudah berjalan
            threads = [
                threading.Thread(target=transcribe_from_microphone),
                threading.Thread(target=translator_thread)
            ]
            for t in threads:
                t.daemon = True
                t.start()
            print("▶️ [GUI] Processes started.")

    def stop_processes(self):
        global threads, stop_flag
        stop_flag = True  # Set flag untuk menghentikan loop di thread
        # Kosongkan audio_queue
        while not audio_queue.empty():
            audio_queue.get()
        threads = []  # Kosongkan daftar thread untuk menghentikan proses
        print("⏹️ [GUI] Processes stopped.")

    def clear_text(self):
        self.text_area_original.delete(1.0, tk.END)
        self.text_area_translated.delete(1.0, tk.END)
        self.text_area_interim.delete(1.0, tk.END)
        print("🧹 [GUI] Text cleared.")

    def update_ui(self):
        # Update panel interim dengan teks dari text queui interim
        while not text_queue_interim.empty():
            sentence = text_queue_interim.get()
            self.text_area_interim.delete(1.0, tk.END)
            self.text_area_interim.insert(tk.END, sentence + "\n")
            self.text_area_interim.see(tk.END)  # scroll otomatis ke bawah

        # Update panel atas dengan teks dari split_text_queue
        while not text_queue_for_gui.empty():
            sentence = text_queue_for_gui.get()
            self.text_area_original.insert(tk.END, sentence + "\n")
            self.text_area_original.see(tk.END)  # scroll otomatis ke bawah

        # Update panel bawah dengan teks dari translated_text_queue
        while not translated_text_queue.empty():
            translated_sentence = translated_text_queue.get()
            self.text_area_translated.insert(
                tk.END, translated_sentence + "\n", "translated_text")
            self.text_area_translated.see(tk.END)  # scroll otomatis ke bawah

        self.root.after(500, self.update_ui)  # cek ulang tiap 500ms


# === Translator Thread ===


def translator_thread():
    global stop_flag
    key = os.getenv("AZURE_TRANSLATOR_KEY")
    location = "southeastasia"
    endpoint = "https://api.cognitive.microsofttranslator.com/translate"
    # lang_url =  "https://api.cognitive.microsofttranslator.com/languages?api-version=3.0"

    # langs_response = requests.get(lang_url).json()
    # print(langs_response)

    params = {
        'api-version': '3.0',
        'from': 'en-US',
        'to': ['id', 'lzh'],
    }

    headers = {
        'Ocp-Apim-Subscription-Key': key,
        # location required if you're using a multi-service or regional (not global) resource.
        'Ocp-Apim-Subscription-Region': location,
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }

    translated_text_queue.put(
        "================= ▶️ started =====================")
    while not stop_flag:
        if not text_queue.empty():
            sentence = text_queue.get()
            # You can pass more than one object in body.
            # Tandai kata-kata tertentu sebelum translasi

            sentence = exclude_words(sentence)
            sentence = mark_custom_words(sentence)

            body = [
                {'text': sentence},
            ]

            request = requests.post(
                endpoint, params=params, headers=headers, json=body)
            response = request.json()
            # [{'translations': [{'text': 'Halo. Halo. Bagaimana keadaanmu?', 'to': 'id'}]}]
            # Iterasi pada hasil JSON untuk mengambil teks translasi
            for translation in response:
                for translated_item in translation.get('translations', []):
                    translated_text = translated_item.get('text', '')
                    # Kembalikan kata-kata yang dikecualikan dan custom translasi
                    print("before restore_excluded_words", translated_text)
                    translated_text = restore_excluded_words(translated_text)
                    print("after restore_excluded_words", translated_text)
                    translated_text = replace_marked_words(translated_text)
                    translated_text_queue.put(translated_text)
                    print("🌍 [Translator] Translated:", translated_text)
            translated_text_queue.put(
                "-------------------------------------------")
            text_queue.task_done()
        else:
            time.sleep(1)
    translated_text_queue.put(
        "================= ⏹️ stopped ====================")


if __name__ == "__main__":
    # Start GUI
    root = tk.Tk()
    gui = TextDisplayGUI(root)
    root.mainloop()
