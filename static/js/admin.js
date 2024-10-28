document.addEventListener('DOMContentLoaded', function() {
  const sidebarToggle = document.createElement('button');
  sidebarToggle.className = 'sidebar-toggle';
  sidebarToggle.innerHTML = '<i class="bi bi-list"></i>';
  document.body.appendChild(sidebarToggle);

  const sidebar = document.getElementById('sidebar');
  const main = document.querySelector('main');

  sidebarToggle.addEventListener('click', function() {
    sidebar.classList.toggle('active');
    main.style.marginLeft = sidebar.classList.contains('active') ? '250px' : '0';
  });

  // Tutup sidebar saat mengklik di luar sidebar pada tampilan mobile
  document.addEventListener('click', function(e) {
    if (window.innerWidth <= 991.98 && 
        !sidebar.contains(e.target) && 
        !sidebarToggle.contains(e.target) && 
        sidebar.classList.contains('active')) {
      sidebar.classList.remove('active');
      main.style.marginLeft = '0';
    }
  });

  // Reset margin saat resize window
  window.addEventListener('resize', function() {
    if (window.innerWidth > 991.98) {
      main.style.marginLeft = '250px';
    } else {
      main.style.marginLeft = sidebar.classList.contains('active') ? '250px' : '0';
    }
  });
});
