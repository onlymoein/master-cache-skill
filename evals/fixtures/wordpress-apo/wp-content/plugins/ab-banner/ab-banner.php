<?php
/* Plugin Name: A/B Banner */
add_action('init', function () {
    if (!isset($_COOKIE['ab_bucket'])) {
        setcookie('ab_bucket', (string) random_int(1, 2), time() + 86400 * 30, '/');
    }
});
