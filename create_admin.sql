-- Periksa apakah user admin sudah ada
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin') THEN
        -- Jika belum ada, buat user admin baru
        INSERT INTO users (username, email, password, role)
        VALUES ('admin', 'admin@example.com', 'scrypt:32768:8:1$QeiLxg2BVWb6xOtf$8d3d2bbc397ce574fa9c3094d0e0b021816d1d2c7265d79c015cef3d1c4295a61b20a63f75fe676d70275bbb5a9e3da5cc1835c0a40caee7c833e3a284c4c268', 'admin');
        
        RAISE NOTICE 'User admin telah dibuat.';
    ELSE
        RAISE NOTICE 'User admin sudah ada.';
    END IF;
END $$;
