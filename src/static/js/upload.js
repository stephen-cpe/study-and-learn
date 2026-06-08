/**
 * Upload page — file list management and AJAX form submission.
 */
(function () {
  'use strict';

  window.initUploadPage = function () {
    var fileInput = document.getElementById('files');
    var fileList = document.getElementById('selected-files-list');
    var form = document.getElementById('unified-form');
    var selectedFiles = [];
    var MAX_FILES = 5;

    function renderFileList() {
      fileList.innerHTML = '';
      if (selectedFiles.length === 0) return;
      selectedFiles.forEach(function (file, index) {
        var li = document.createElement('li');
        li.className = 'file-item d-flex justify-content-between align-items-center p-2 mb-2';
        li.innerHTML =
          '<span class="text-truncate">' +
          '\uD83D\uDCC4 ' + file.name +
          ' <small class="text-muted">(' + (file.size / 1024).toFixed(1) + ' KB)</small></span>' +
          '<button type="button" class="btn btn-sm btn-outline-danger ms-2 remove-btn" data-index="' + index + '">\u2716</button>';
        fileList.appendChild(li);
      });
      document.querySelectorAll('.remove-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          var idx = parseInt(e.currentTarget.dataset.index);
          selectedFiles.splice(idx, 1);
          if (selectedFiles.length < MAX_FILES) {
            fileInput.disabled = false;
            fileInput.title = '';
          }
          renderFileList();
        });
      });
    }

    fileInput.addEventListener('change', function (e) {
      var newFiles = Array.from(e.target.files);
      newFiles.forEach(function (file) {
        var exists = selectedFiles.some(function (f) {
          return f.name === file.name && f.size === file.size;
        });
        if (!exists && selectedFiles.length < MAX_FILES) {
          selectedFiles.push(file);
        }
      });
      if (selectedFiles.length >= MAX_FILES) {
        fileInput.disabled = true;
        fileInput.title = 'Maximum ' + MAX_FILES + ' files reached';
      }
      renderFileList();
      fileInput.value = '';
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var goalInput = document.getElementById('learning_goal');
      if (!goalInput.value.trim()) {
        goalInput.focus();
        return;
      }
      if (selectedFiles.length === 0) {
        fileInput.focus();
        return;
      }
      var submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Processing...';
      var taskId = window.generateTaskId();
      window.setBubblePersistent('Receiving your study materials...');
      window.showBubbleBar(0);
      var formData = new FormData();
      formData.append('learning_goal', goalInput.value.trim());
      formData.append('task_id', taskId);
      selectedFiles.forEach(function (file) {
        formData.append('files', file);
      });
      fetch(form.action, { method: 'POST', body: formData })
        .then(function (response) {
          if (response.ok) {
            var ct = (response.headers.get('content-type') || '');
            if (ct.indexOf('application/json') !== -1) {
              return response.json().then(function (data) {
                if (data.redirect) {
                  window.location.href = data.redirect;
                } else if (data.error) {
                  window._mascotTalk(data.error);
                  window.showBubbleBar(0);
                  window._progressActive = false;
                  submitBtn.disabled = false;
                  submitBtn.textContent = 'Process My Learning Materials';
                }
              });
            }
            window.location.href = response.url;
            return;
          }
          response.json().then(function (data) {
            var msg = (data && data.error) ? data.error : 'Upload failed. Please try again.';
            window._mascotTalk(msg);
            window.showBubbleBar(0);
            window._progressActive = false;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Process My Learning Materials';
          }).catch(function () {
            window._mascotTalk('Upload failed. Please try again.');
            window.showBubbleBar(0);
            window._progressActive = false;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Process My Learning Materials';
          });
        })
        .catch(function () {
          window._mascotTalk('Network error. Please try again.');
          window.showBubbleBar(0);
          window._progressActive = false;
        });

      window.startProcessProgressPoll(taskId);
    });
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('unified-form')) {
      window.initUploadPage();
    }
  });
})();
