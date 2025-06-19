document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const menuBtn = document.querySelector('.menu-btn');
    const navLinks = document.querySelector('.nav-links');

    // Hamburger menu toggle for mobile
    if (menuBtn && navLinks) {
        menuBtn.addEventListener('click', function(e) {
            e.stopPropagation(); // Prevent event bubbling
            navLinks.classList.toggle('active');
            menuBtn.classList.toggle('active');
            if (navLinks.classList.contains('active')) {
                navLinks.style.animation = 'slideDown 0.3s ease';
            } else {
                navLinks.style.animation = 'slideUp 0.2s ease';
            }
        });
    }

    // Close mobile menu when clicking outside or on a nav link
    document.addEventListener('click', function(e) {
        if (navLinks.classList.contains('active') && !e.target.closest('.navbar')) {
            navLinks.classList.remove('active');
            menuBtn.classList.remove('active');
            navLinks.style.animation = 'slideUp 0.2s ease';
        }
    });
    navLinks && navLinks.querySelectorAll('a').forEach(function(link) {
        link.addEventListener('click', function() {
            navLinks.classList.remove('active');
            menuBtn.classList.remove('active');
            navLinks.style.animation = 'slideUp 0.2s ease';
        });
    });

    // Image upload preview
    const imageUpload = document.getElementById('imageUpload');
    const imagePreview = document.getElementById('imagePreview');
    const uploadForm = document.getElementById('uploadForm');
    const resultSection = document.getElementById('resultSection');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const downloadReportBtn = document.getElementById('downloadReportBtn');

    if (imageUpload) {
        imageUpload.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    imagePreview.src = e.target.result;
                    imagePreview.style.display = 'block';
                }
                reader.readAsDataURL(file);
            }
        });
    }

    if (uploadForm) {
        uploadForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            try {
                loadingSpinner.style.display = 'block';
                const response = await fetch('/detect', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                if (result.error) {
                    alert(result.error);
                    return;
                }
                // Display results
                resultSection.innerHTML = `
                    <h3>Analysis Results</h3>
                    <img src="${result.image_url}" alt="Uploaded Image" style="max-width: 300px; display: block; margin-bottom: 10px;" />
                    <pre>Prediction: ${result.predicted_label}</pre>
                    <button id="downloadReportBtn" class="btn btn-primary">Download PDF Report</button>
                `;
                resultSection.style.display = 'block';
                // Attach download event
                const downloadBtn = document.getElementById('downloadReportBtn');
                if (downloadBtn) {
                    downloadBtn.addEventListener('click', async function() {
                        // Prepare report data
                        const reportData = {
                            report_id: 'RPT-' + Date.now(),
                            report_date: new Date().toISOString().slice(0, 10),
                            report_time: new Date().toLocaleTimeString(),
                            patient_name: document.getElementById('patientName')?.value || 'Anonymous',
                            condition_name: result.predicted_label,
                            confidence: result.class_probabilities ? (Math.max(...Object.values(result.class_probabilities)).toFixed(2) * 100 + '%') : 'N/A',
                            image_url: result.image_url
                        };
                        const pdfResponse = await fetch('/download_latest_report', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(reportData)
                        });
                        if (pdfResponse.ok) {
                            const blob = await pdfResponse.blob();
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `DermaVision_Report_${reportData.report_id}.pdf`;
                            document.body.appendChild(a);
                            a.click();
                            a.remove();
                            window.URL.revokeObjectURL(url);
                        } else {
                            alert('Failed to generate PDF report.');
                        }
                    });
                }
            } catch (error) {
                console.error('Error:', error);
                alert('An error occurred while processing your request.');
            } finally {
                loadingSpinner.style.display = 'none';
            }
        });
    }
    setupThemeToggle();
    setupPasswordToggle();
});
