// ==UserScript==
// @name         Scroll To Bottom Button
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  在所有页面右下角悬浮一个按钮，点击后滚动到底部，检测异步加载后停止。
// @author       Your Name
// @match        *://*/*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    // 创建悬浮按钮
    const button = document.createElement('button');
    button.innerText = '向下滚动到底';
    button.style.position = 'fixed';
    button.style.bottom = '20px';
    button.style.right = '20px';
    button.style.zIndex = '10000';
    button.style.padding = '10px 20px';
    button.style.backgroundColor = '#008CBA';
    button.style.color = 'white';
    button.style.border = 'none';
    button.style.borderRadius = '5px';
    button.style.cursor = 'pointer';
    button.style.fontSize = '14px';
    button.style.boxShadow = '0 2px 5px rgba(0,0,0,0.3)';
    document.body.appendChild(button);

    // 初始化状态标志位
    let scrolling = false;

    // 检测是否页面异步加载完成
    const isContentLoaded = () => {
        return document.readyState === 'complete' && !isLoadingNewContent();
    };

    const isLoadingNewContent = () => {
        // 检测页面是否有动态加载标志
        const loadingIndicators = document.querySelectorAll('[data-loading], .loading, .spinner, .loader');
        return Array.from(loadingIndicators).some(el => el.offsetParent !== null); // 元素是否可见
    };

    // 自动滚动到页面底部
    const scrollToBottom = () => {
        scrolling = true;
        const scrollInterval = setInterval(() => {
            if (!scrolling || isContentLoaded()) {
                clearInterval(scrollInterval);
                scrolling = false;
            } else {
                window.scrollBy(0, 50);
            }
        }, 50);
    };

    // 按钮点击事件
    button.addEventListener('click', () => {
        if (!scrolling) {
            scrollToBottom();
        }
    });
})();
