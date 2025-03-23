console.log('Скрипт модального окна загружен');

document.addEventListener('DOMContentLoaded', function() {
    try {
        const certificates = document.querySelectorAll('.service__image');
        const modal = document.querySelector('.certificate-modal');
        const modalImg = document.querySelector('.certificate-modal__image');
        const closeBtn = document.querySelector('.certificate-modal__close');

        if (!modal || !modalImg || !closeBtn) {
            console.error('Не найдены элементы модального окна');
            return;
        }

        console.log(`Найдено сертификатов: ${certificates.length}`);

        certificates.forEach(cert => {
            if (!cert.classList.contains('certificate-initialized')) {
                cert.classList.add('certificate-initialized');
                
                cert.addEventListener('click', function(e) {
                    if (this.closest('a')) {
                        // Если это ссылка на массаж, не открываем модальное окно
                        return;
                    }
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const bgImage = this.style.backgroundImage;
                    if (!bgImage) {
                        console.error('Не найдено фоновое изображение');
                        return;
                    }
                    
                    const imageUrl = bgImage.slice(4, -1).replace(/['"]/g, '');
                    console.log('Открываем изображение:', imageUrl);
                    
                    modalImg.src = imageUrl;
                    modal.classList.add('active');
                    document.body.style.overflow = 'hidden';
                });
            }
        });

        closeBtn.addEventListener('click', function(e) {
            e.preventDefault();
            modal.classList.remove('active');
            document.body.style.overflow = '';
        });

        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        });

        // Предзагрузка изображений
        certificates.forEach(cert => {
            if (cert.closest('a')) return; // Пропускаем ссылки на массаж
            
            const bgImage = cert.style.backgroundImage;
            if (bgImage) {
                const imageUrl = bgImage.slice(4, -1).replace(/['"]/g, '');
                const img = new Image();
                img.src = imageUrl;
            }
        });
    } catch (error) {
        console.error('Ошибка в скрипте модального окна:', error);
    }
}); 