# Teknik bilgi ve doğrulanmış gözlemler

## Doğrulanmış

- Uygulama Python 3.10+ standart kütüphanesiyle çalışır; CLI `ctxzip.py` içindedir.
- 2026-09-25'te Windows/Python 3.12 ile `--help`, `topla`, `dokum`, `durum` ve `ozetle --proje Godot-AI-Sidebar --elle` çalıştırıldı. İlk toplamada 48 kaynak kopyalandı; Godot-AI-Sidebar için 11 bekleyen Bölüm oluştu. Bu, özet kalitesini veya gerçek LLM bağlantısını kanıtlamaz.
- `raw/` kaynağın kopyasıdır ve kaynak büyüdüğünde güncellenir. Kaynak küçülürse eski kopya `*.onceki.jsonl` olarak saklanır.
- `BAGLAM.md` yalnızca doldurulmuş özetleri seçer; seçim yeniye öncelik ve yaklaşık token bütçesiyledir.

## Belirsizlikler

- Bu makinede 9Router portu açık olsa da `/v1/models` isteği zaman aşımına uğradı. Gerçek LLM özetlemesi doğrulanmadı.
- Claude Code/Codex JSONL alanları sürümler arasında değişebilir. Antigravity `brain/` yolu tam sohbeti sağlamaz.
- `len(metin)/3.5` gerçek token sayısı değildir; gizli kalıp temizleyici bütün sırları bulamaz.

## İlkeler

Ham arşivi, ayarları ve bağlam paketini açık depoya koyma. Özetteki test veya davranış iddiasını güncel commit ve test çıktısıyla yeniden doğrula. Yeni kaynak biçimini kişisel verisi temizlenmiş gerçek örnekle test et.
