/* Fix for ace-editor. It thinks it's in the admin only */
(function () {
    if (window.jQuery !== undefined) {
        window.django = {
            'jQuery': window.jQuery
        };
    }
})();
