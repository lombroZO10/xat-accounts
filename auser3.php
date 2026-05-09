<?php
// 🔧 Força CORS correto, substitui qualquer valor anterior errado
if (function_exists('header_remove')) {
}
if (isset($_SERVER["HTTP_ORIGIN"])) { $origin = $_SERVER["HTTP_ORIGIN"]; $allowed = ["https://oxat.in", "https://me.oxat.in"]; if (in_array($origin, $allowed)) { header("Access-Control-Allow-Origin: $origin"); } } else { header("Access-Control-Allow-Origin: https://oxat.in"); };
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");

// ===========================
// Auser3 público (bridge seguro)
// ===========================

// Simula ambiente HTTP quando necessário (CLI / include)
if (php_sapi_name() === 'cli' || empty($_SERVER['REQUEST_METHOD'])) {
    $_SERVER['REQUEST_METHOD'] = 'GET';
    $_SERVER['HTTP_HOST'] = 'oxat.in';
    $_SERVER['REQUEST_URI'] = '/bot/auser3.php';
    $_SERVER['REMOTE_ADDR'] = '127.0.0.1';
    $_SERVER['HTTP_USER_AGENT'] = 'Mozilla/5.0 (compatible; PHP bot bridge)';
}

// Caminhos base
define('DIRECTORY', '/var/www/vhosts/oxat.in/httpdocs');
define('SEPARATOR', '/');

// Carrega autoload do sistema
require_once DIRECTORY . SEPARATOR . 'app' . SEPARATOR . 'autoload.php';

error_reporting(E_ALL);
ini_set('display_errors', 0);

// Headers básicos
if (isset($_SERVER["HTTP_ORIGIN"])) { $origin = $_SERVER["HTTP_ORIGIN"]; $allowed = ["https://oxat.in", "https://me.oxat.in"]; if (in_array($origin, $allowed)) { header("Access-Control-Allow-Origin: $origin"); } } else { header("Access-Control-Allow-Origin: https://oxat.in"); };
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");
header("Content-Type: application/json; charset=utf-8");

// Pré-flight CORS
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// Simulação de ambiente real (para \Server::isRealUser e outros)
$_SERVER['HTTP_USER_AGENT']  = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)';
$_SERVER['HTTP_REFERER']     = 'https://oxat.in/';
$_SERVER['REMOTE_ADDR']      = $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1';
$_COOKIE['PHPSESSID']        = $_COOKIE['PHPSESSID'] ?? session_id();
$_SESSION['verified']        = true;
$_SESSION['realuser']        = true;
$_SESSION['allow']           = true;
$_SERVER['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest';

// Caminho real do script original
$realFile = DIRECTORY . '/app/functions/web_gear/Auser3.php';

try {
    if (!file_exists($realFile)) {
        throw new Exception("Arquivo original não encontrado: $realFile");
    }

    // Primeiro tenta via classe (caso exista)
    if (class_exists('Functions\\WebGear\\Auser3')) {
        $auser = new \Functions\WebGear\Auser3();
        $auser->index();
        exit;
    }

    // Caso contrário, apenas inclui o script diretamente (script procedural)
    require_once $realFile;

} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode([
        'Err' => 'Erro ao executar Auser3: ' . $e->getMessage()
    ]);
}
