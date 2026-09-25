# AGENTS.md — CtxZip ajan kılavuzu

Bu dosya CtxZip deposunda çalışan Codex, Claude Code, Antigravity ve diğer kodlama ajanları içindir. Güncel davranışın kaynağı `ctxzip.py` ve test sonuçlarıdır; bu dosyadaki geçmiş gözlemler güncel doğrulamanın yerine geçmez.

## Proje amacı

CtxZip, farklı AI kodlama araçlarının yerel oturumlarını proje bazında arşivler, okunabilir döküme çevirir, Bölüm/Cilt özetleri oluşturur ve yeni sohbet için `BAGLAM.md` hazırlar. Python 3.10+ standart kütüphanesiyle çalışan bir CLI'dır. Komut akışı `ctxzip.py`; gizlilik, LLM ve Git sınırları `ctxzip_core/` içindedir.

## İşe başlarken

1. `README.md`, `ARCHITECTURE.md`, `docs/KNOWLEDGE.md` dosyalarını ve göreve göre `docs/PLAN.md` / `docs/TASKS.md` dosyalarını oku.
2. `git status --short` ile çalışma ağacını kontrol et. Kullanıcının mevcut değişikliklerini koru.
3. İlgili kod yolunu ve kaynak biçimini incele; eski bir özetin iddiasını kanıt sayma.
4. Yeni özellik veya davranış değişikliğinde README, mimari, görevler ve CHANGELOG etkisini değerlendir.

## Veri sınırları

- `~/CtxZip-Arsiv`, `raw/`, `dokum/`, `bolumler/`, `ciltler/`, `gelen/`, `BAGLAM.md`, `ctxzip_ayar.json` ve `.env` kişisel veri veya sır içerebilir. Bunları açık depoya, örnek dosyaya, issue'ya veya model istemine gelişigüzel koyma.
- Gerçek oturumlarla test gerekiyorsa yalnızca gereken en küçük kesiti kullan; kalıcı test fikstürüne koymadan önce kişisel veriyi çıkar ve yeniden kontrol et.
- `gizli_temizle` sınırlı bir savunmadır. Bütün sırları bulduğunu veya LLM'e veri göndermenin güvenli olduğunu iddia etme.
- `--elle` modunda otomatik LLM çağrısı yapılmaz. Otomatik özetlemede seçilen sağlayıcıya metin gönderilir; bu ayrımı koru.
- LLM önizlemesi ve varsayılan onay kapısını kaldırma. `--onayli-gonder` yalnızca kullanıcının açık otomasyon tercihidir.
- Commit koruması index'i tarar; yeni klonda `scripts/install_hook.py` gerekir. Mevcut hook'u silme veya sessizce değiştirme.

## Davranış değişmezleri

- Ham kayıt ve güncel kod, özetlerden üstündür. Özet yanlış veya eski olabilir.
- Bir Bölüm yalnızca tek oturumun tur aralığını kapsar. Aktif oturumun son parçası kapanma eşiğine kadar bekler.
- Doldurulmamış Bölümler Cilt'e veya `BAGLAM.md` paketine girmez.
- Kullanıcının elle düzelttiği özetleri yeniden çalıştırırken koru.
- `durum.json`, Bölüm/Cilt dosyaları ve kaynak tur aralıkları tutarlı kalmalı. Yarım başarısızlıkta veri kaybını önle.
- Proje eşlemesini, kaynak turu/commit atfını ve bağlam bütçesini sessizce değiştirme.
- Bağımlılık yönünü `ctxzip.py → ctxzip_core` olarak koru. Çekirdek modüller CLI'ı içe aktarmasın; ayrıştırıcıları ve özetleme durumunu ileride küçük, testli adımlarla taşı.
- Antigravity desteğini tam transkript olarak sunma: mevcut kod erişilen Markdown artefaktlarını toplar.

## Doğrulama

- En azından `python ctxzip.py --help` ve değişen komutun dar kapsamlı bir denemesini çalıştır.
- Parser veya özetleme mantığı değişirse kişisel verisi temizlenmiş gerçek biçim örnekleriyle; tekrar çalıştırma, büyüyen/kısalan kaynak, manuel düzeltme ve hata sonrası devam senaryolarını sınamayı tercih et.
- Ağ/LLM davranışını mock veya `--elle` testiyle doğrulanmış sayma. Gerçek sağlayıcı testi yapılmadıysa açıkça belirt.
- Test komutunu ve sonucu raporla. Test edilemeyen davranışı doğrulanmış gibi yazma.

## Belge haritası

- `README.md`: kullanıcı kurulumu ve sınırlar.
- `ARCHITECTURE.md`: veri akışı ve katmanlar.
- `ROADMAP.md`: hedef sürümler.
- `docs/PLAN.md`: uygulama aşamaları; `docs/TASKS.md`: açık işler.
- `docs/KNOWLEDGE.md`: doğrulanmış teknik bilgi ve belirsizlikler.
- `CHANGELOG.md`: kullanıcıya görünür değişiklikler.

Görev kapsamını genişletmeden önce mevcut hedefi bitir; yeni fikirleri ilgili plan veya görev belgesine kaydet.
