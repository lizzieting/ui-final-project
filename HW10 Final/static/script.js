document.addEventListener('DOMContentLoaded', function() {
    const progressBar = document.querySelector('.quiz-progress');
    if (progressBar) {
        const currentQuestion = parseInt(progressBar.getAttribute('aria-valuenow'));
        const totalQuestions = parseInt(progressBar.getAttribute('aria-valuemax'));
        const width = (currentQuestion / totalQuestions) * 100;
        progressBar.style.width = `${width}%`;
    }
}); 