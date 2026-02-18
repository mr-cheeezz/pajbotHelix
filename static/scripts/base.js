$.fn.api.settings.api = {
    get_user: '/api/v1/users/{username}',
    get_user_from_user_input: '/api/v1/users/{username}?user_input=true',
    edit_command: '/api/v1/commands/update/{id}',
    remove_command: '/api/v1/commands/remove/{id}',
    check_alias: '/api/v1/commands/checkalias',
    toggle_timer: '/api/v1/timers/toggle/{id}',
    remove_timer: '/api/v1/timers/remove/{id}',
    toggle_banphrase: '/api/v1/banphrases/toggle/{id}',
    remove_banphrase: '/api/v1/banphrases/remove/{id}',
    toggle_module: '/api/v1/modules/toggle/{id}',
    social_set: '/api/v1/social/{key}/set',
    commands: '/api/v1/commands/{raw_command_id}',
};

var THEME_STORAGE_KEY = 'pajbot_theme';

function getStoredTheme() {
    try {
        return localStorage.getItem(THEME_STORAGE_KEY);
    } catch (e) {
        return null;
    }
}

function setStoredTheme(theme) {
    try {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch (e) {}
}

function getPreferredTheme() {
    var stored = getStoredTheme();
    if (stored === 'light' || stored === 'dark') {
        return stored;
    }

    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
    }

    return 'light';
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
}

function updateThemeToggleLabel(theme) {
    var toggle = $('#theme-toggle');
    if (!toggle.length) {
        return;
    }

    var icon = toggle.find('.theme-toggle-icon');
    var label = toggle.find('.theme-toggle-label');
    if (theme === 'dark') {
        icon.removeClass('moon').addClass('sun');
        label.text('Light mode');
    } else {
        icon.removeClass('sun').addClass('moon');
        label.text('Dark mode');
    }
}

function initThemeToggle() {
    var toggle = $('#theme-toggle');
    if (!toggle.length) {
        return;
    }

    var currentTheme = getPreferredTheme();
    applyTheme(currentTheme);
    updateThemeToggleLabel(currentTheme);

    toggle.on('click', function() {
        currentTheme = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        applyTheme(currentTheme);
        setStoredTheme(currentTheme);
        updateThemeToggleLabel(currentTheme);
    });
}

$(document).ready(function() {
    initThemeToggle();

    $('#usersearch').form({
        fields: {
            username: 'empty',
        },
        onSuccess: function(settings) {
            document.location.href =
                '/user/' +
                encodeURIComponent($('#usersearch input.username').val());
            return false;
        },
    });
});

// parseUri 1.2.2
// (c) Steven Levithan <stevenlevithan.com>
// MIT License

function parseUri(str) {
    var o = parseUri.options,
        m = o.parser[o.strictMode ? 'strict' : 'loose'].exec(str),
        uri = {},
        i = 14;

    while (i--) uri[o.key[i]] = m[i] || '';

    uri[o.q.name] = {};
    uri[o.key[12]].replace(o.q.parser, function($0, $1, $2) {
        if ($1) uri[o.q.name][$1] = $2;
    });

    return uri;
}

parseUri.options = {
    strictMode: false,
    key: [
        'source',
        'protocol',
        'authority',
        'userInfo',
        'user',
        'password',
        'host',
        'port',
        'relative',
        'path',
        'directory',
        'file',
        'query',
        'anchor',
    ],
    q: {
        name: 'queryKey',
        parser: /(?:^|&)([^&=]*)=?([^&]*)/g,
    },
    parser: {
        strict: /^(?:([^:\/?#]+):)?(?:\/\/((?:(([^:@]*)(?::([^:@]*))?)?@)?([^:\/?#]*)(?::(\d*))?))?((((?:[^?#\/]*\/)*)([^?#]*))(?:\?([^#]*))?(?:#(.*))?)/,
        loose: /^(?:(?![^:@]+:[^:@\/]*@)([^:\/?#.]+):)?(?:\/\/)?((?:(([^:@]*)(?::([^:@]*))?)?@)?([^:\/?#]*)(?::(\d*))?)(((\/(?:[^?#](?![^?#\/]*\.[^?#\/.]+(?:[?#]|$)))*\/?)?([^?#\/]*))(?:\?([^#]*))?(?:#(.*))?)/,
    },
};
