<?php
namespace Functions\WebGear\User;

// Permitir acesso de qualquer origem
if (isset($_SERVER["HTTP_ORIGIN"])) { $origin = $_SERVER["HTTP_ORIGIN"]; $allowed = ["https://oxat.in", "https://me.oxat.in"]; if (in_array($origin, $allowed)) { header("Access-Control-Allow-Origin: $origin"); } } else { header("Access-Control-Allow-Origin: https://oxat.in"); };
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");

// Responde rápido a requisições de pré-verificação (CORS)
if ($_SERVER['REQUEST_METHOD'] == 'OPTIONS') {
    http_response_code(200);
    exit;
}

use Classes\User;
use Classes\Core;
use Vendor\Header;
use Vendor\View;
use Vendor\Validator;
use Vendor\SMTP;
use Vendor\PHPMailer;

class Register5 {
	protected $user;
	protected $chat;
	protected $core;
	protected $mail;
	
	public function __construct() {
		$this->user = new User();
		$this->core = new Core();
		$this->mail = new PHPMailer();
	}
	
	private function DoLogin(string $user = '0', string $password = '$0', int $chat = 2) {
		return '<div class="text-success font-weight-bold mb-3" data-localize="web.logoutsuccess">You have been successfully logged out!</div>';
	}


	private function isBad(string $name): bool {
		$name = strtolower($name);
		foreach (NOT_ALLOW as $n) {
			if (strpos($name, $n) !== false) {
				return true;
			}
		}
		return false;
	}

	public function index() {
		if (\Server::isRealUser() == false) {
			return http_response_code(403);
		}
		$agree      	= (string) \Server::post('agree');
		$youremail  	= (string) \Server::post('YourEmail');
		$NameEmail  	= (string) \Server::post('NameEmail');
		$Username 	 	= (string) \Server::post('Username');
		$password   	= (string) \Server::post('password');
		$password2   	= (string) \Server::post('password2');
		$oldpassword   	= (string) \Server::post('oldpassword');
		$Protected   	= (string) \Server::post('Protected');
		$Locked   		= (string) \Server::post('Locked');
		$PassHash   	= (string) \Server::post('PassHash');
		$DeviceId   	= (string) \Server::post('DeviceId');
		$ResetApiKey    = (string) \Server::post('ResetApiKey');
		$captcha 		= (string) \Server::post('g-recaptcha-response');
		$ac 			= (string) \Server::post('ac');
		$email 			= (string) \Server::post('email');
		$key 			= (string) \Server::post('key');
		$UserId     	= (int) \Server::post('UserId');
		$k2	         	= (int) \Server::post('k2');
		$Logout     	= (int) \Server::post('Logout');
		$Delete     	= (int) \Server::post('Delete');
		$Login     		= (int) \Server::post('Login');
		$ChangeUserName = (int) \Server::post('ChangeUserName');
		$ForgotPassword = (int) \Server::post('ForgotPassword');
		$ChangePassword = (int) \Server::post('ChangePassword');
		$Pin        	= (int) \Server::post('Pin');
		$DoneQuiz       = (int) \Server::post('DoneQuiz');
		$Register       = (int) \Server::post('Register');
		$mode       	= (int) \Server::post('mode');
		$Options        = [$Logout, $Delete, $Login, $ChangeUserName, $ForgotPassword, $ForgotPassword, $ChangePassword, $Pin, $DoneQuiz, $Register, $mode];
		$Err        	= ['Err' =>[]];
		$getJson = (string) \Server::post('json');
		$json = json_decode($getJson, false);
		$juser = strip_tags($json->name);
		$jpass = strip_tags($json->password);
		$jemail = strip_tags($json->email);
		$jnemail = strip_tags($json->NameEmail);
		$jForgotPassword = strip_tags($json->ForgotPassword);
		
		
		
		
		
		
		
		
		
		while(1) {
			
			
			if (!empty($juser) && !empty($jpass) && !empty($jemail)) {
							$stop = 0;
							
							if (strlen($juser) < 10) {
								return View::plain('<span data-localize=buy.short>Name is too short</span> E47');
								$stop = 1;
							}
							if (strlen($juser) > 18  ||  !Validator::isAlphanumeric($juser)) {
								return View::plain('<span data-localize=login.namebad>Name was too long or contains bad letters</span> E47');
								$stop = 1;
							}
							if (Validator::isNumeric(substr($juser, 0, 1))) {
								return View::plain('<span data-localize=buy.firstletter>First letter must not be a number.</span>');
								$stop = 1;
							}
							if ($this->isBad($juser)) {
								return View::plain('<span data-localize=buy.notallowed>Name is not allowed. Please try another.</span>');
								$stop = 1;
							}
							if ($this->user->isAlreadyRegistered($juser)) {
								return View::plain('<span data-localize=login.namedup>Username is now taken. Please try another name</span> E6');
								$stop = 1;
							}
							
							if (!Validator::isAlphanumeric($jpass)) {
								return View::plain('<span data-localize=login.len6>At least 6 letters, case sensitive, 0-9,A-Z,a-z only</span> E65');
								$stop = 1;
							}					
							if (strlen($jpass) < 6) {
								return View::plain('<span data-localize=login.passshort>Password was too short</span> E39');
								$stop = 1;
							}
							
							$explode = explode('@', $jemail);
							if (!in_array($explode[1], ALLOW_EMAIL)) {
								return View::plain('<span data-localize=main.evalid>email is not valid</span> E42');
								$stop = 1;
							}
							$getEmail = $this->user->getUserEmail($jemail);
							if ($getEmail) {
								return View::plain('<span data-localize=login.emaildup>Email is used. Please try another email</span>. E7');
								$stop = 1;
							}
							//if (!$this->user->checkMaxAccounts()) {
							//	return View::plain('<span data-localize=login.emaildup>You exceeded the maximum number of registrations allowed</span>');
							//	$stop = 1;
							//}
							if (!$_last->id == 0) {
								return View::plain('Fuck id is blocked'); // id ok ? super delete register 2 3 
								$stop = 1;
							}
							if ($stop == 1) { break; }
							$_last = $this->user->getLastGuest();
							$this->user->deleteData('users',['id' => $_last->id, 'k2' => $_last->k2]);
							$RegisterCode = $this->core->rand(10);
							$userdetails  = $this->core->userdetails($this->user->ipAddr());
							$this->user->doRegister($_last->id, $_last->k, $_last->k2, $_last->k3, $juser, $jpass, $jemail, $userdetails['isp'], $userdetails['country'], $RegisterCode);
							if (smtpmail == true) {	
							
								$this->mail->IsSMTP();
								$this->mail->SMTPAuth   = true;
								$this->mail->SMTPSecure = SMTP_Sec;
								$this->mail->Host       = host_smtp;
								$this->mail->Port       = port_gmail;
								$this->mail->Username   = mail_gmail;
								$this->mail->Password   = pass_gmail;
								$this->mail->From       = mail_gmail;              
								$this->mail->FromName   = 'INFO ' . XAT_NAME;
								$this->mail->Subject    = \Server::PrintMessage('login', 'activate1',[$juser]);
								$this->mail->AltBody    = "";
								$this->mail->Body       = "";
								$this->mail->Body      .= \Server::PrintMessage('login', 'activate2',[$juser, METHOD . '//' . DOMAIN .'/login?UserId='.$_last->id.'&k2='.$_last->k2.'&ac='.$RegisterCode.'&mode=1', $juser]);
								$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'. DOMAIN .'/'. XAT_NAME, FACEBOOK]);
								$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
								$this->mail->AddAddress($jemail, "");
								$this->mail->IsHTML(false);
								$this->mail->Send();
								
							}
							$data = (object) array(
								'UserId' => $_last->id,
								'k1' => $_last->k,
								'k2' => $_last->k2,
								'html' => '<p>Thank you, your registration has been processed.<BR>A confirmation e-mail has been sent. Please click on the link in that email to activate your username.</p><p><strong>IMPORTANT: If you do not receive an email check your spam inbox.</strong></p><p><strong>(The email could take up to 30 minutes to arrive.)</strong></p>'
							);
							
							$message = $data;
							echo json_encode($message);
							
		}
		if ($jForgotPassword == "ResetPassword"){
					if (!Validator::isValidEmail($jnemail)) {
						return View::plain('<span data-localize=main.evalid>email is not valid</span> E42');
						break;
					}
					$user = $this->user->getUserEmail($jnemail);
					if (!$user) {
						return View::plain(''.$jnemail.' <span data-localize=buy.notfound>not found</span>. E17');
						break;
					}else{
						$data = (object) array(
								'html' => '<p>An e-mail has been sent. Please click on the link in that email to set a new password<\/p><p><strong>IMPORTANT: If you do not receive an email check your spam inbox.<\/strong><\/p><p><strong>(the email could take up to 30 minutes to arrive)<\/strong><\/p>'
								);
						$message = $data;
						echo json_encode($message);
					}
					if (smtpmail == true) {
						
						$forgotHash = $this->core->rand(10);
						$this->user->updateData('users', ['forgothash' => $forgotHash], ['id' => $user->id]);
						$this->mail->IsSMTP();
						$this->mail->SMTPAuth   = true;
						$this->mail->SMTPSecure = SMTP_Sec;
						$this->mail->Host       = host_smtp;
						$this->mail->Port       = port_gmail;
						$this->mail->Username   = mail_gmail;
						$this->mail->Password   = pass_gmail;
						$this->mail->From       = mail_gmail;              
						$this->mail->FromName   = 'INFO ' . XAT_NAME;
						$this->mail->Subject    = \Server::PrintMessage('login', 'chgpass1',[$user->username]);
						$this->mail->AltBody    = "";
						$this->mail->Body       = "";
						$this->mail->Body      .= \Server::PrintMessage('login', 'chgpass2',[$user->username, METHOD.'//'.DOMAIN.'/login?UserId='.$user->id.'&k2='.$user->k2.'&key='.$forgotHash.'&mob=0']);
						$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'.DOMAIN.'/'. XAT_NAME, FACEBOOK]);
						$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
						$this->mail->AddAddress($user->email, "");
						$this->mail->IsHTML(false);
						$this->mail->Send();
					}
			
			break;
		}
		
			
			
			
			
			
			
			
			if (Validator::spam_control($this->user->ipAddr(),'login')) {
				$Err['Err']['login'] = 'Try again in 10 minutes';
				break; 			
			}
			switch($Options){
				case $Logout && $Logout == 1:
					$this->user->doLogout();
					$Err['Err']['LogoutEmbed'] = $this->DoLogin();
				break;
				case $Login && $Login == 1:
				case $Delete && $Delete == 1:
				case $ChangeUserName && $ChangeUserName == 1:
					$abc = 'login';
					$abcc = $this->user->disablepages($abc);
					if ($abcc->login == 0){
						$Err['Err']['login'] = 'Sorry not allowed you '.$abc.' this website';
						break;
					}
					if (!Validator::isAlphanumeric($NameEmail)) {
						$Err['Err']['login'] = $NameEmail . ':Wrong username/email or password E25';
						break; 
					}
					$user = $this->user->getUserByUsername($NameEmail);
					if (!$user || !$this->core->validate($password, $user->password)) {
						$Err['Err']['login'] = $NameEmail . ':Wrong username/email or password E25';
						break; 
					}
					$Confirmed = ($user->confirmed == 1 ? true : false);
					if (!$Confirmed) {
						if (smtpmail == true) {	
						
							$Code = $this->core->rand(10);
							$this->user->updateData('users', ['confirmed' => $Code], ['username' => $user->username]);
							$this->mail->IsSMTP();
							$this->mail->SMTPAuth   = true;
							$this->mail->SMTPSecure = SMTP_Sec;
							$this->mail->Host       = host_smtp;
							$this->mail->Port       = port_gmail;
							$this->mail->Username   = mail_gmail;
							$this->mail->Password   = pass_gmail;
							$this->mail->From       = mail_gmail;              
							$this->mail->FromName   = 'INFO ' . XAT_NAME;
							$this->mail->Subject    = \Server::PrintMessage('login', 'activate1',[$user->username]);
							$this->mail->AltBody    = "";
							$this->mail->Body       = "";
							$this->mail->Body      .= \Server::PrintMessage('login', 'activate2',[$user->username, METHOD . '//' . DOMAIN .'/login?UserId='.$user->id.'&k2='.$user->k2.'&ac='.$Code.'&mode=1', $user->username]);
							$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'. DOMAIN .'/'. XAT_NAME, FACEBOOK]);
							$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
							$this->mail->AddAddress($user->email, "");
							$this->mail->IsHTML(false);
							$this->mail->Send();
							
						}
						$Err['Err']['login'] = $user->username .' '. \Server::PrintResult('buy','notconf');
						break;
					}
					$userdetails = $this->core->userdetails($this->user->ipAddr());
					switch($user->protection) {
						case 'ip':
							$protection = ($user->ip_login != $this->user->ipAddr()) ? true : false;
						break;
						case 'isp':
							$protection = ($user->isp != $userdetails['isp']) ? true : false;
						case 'country':
							$protection = ($user->country != $userdetails['country']) ? true : false;
						break;
					}
					if ((!$Pin || $user->pin != $Pin) && $protection)
					{					  
						if (smtpmail == true) {
							$PinCode = rand(1, 10000000000);
							$this->user->updateData('users', ['pin' => $PinCode ], ['username' => $user->username]);
							$this->mail->IsSMTP();
							$this->mail->SMTPAuth   = true;
							$this->mail->SMTPSecure = SMTP_Sec;
							$this->mail->Host       = host_smtp;
							$this->mail->Port       = port_gmail;
							$this->mail->Username   = mail_gmail;
							$this->mail->Password   = pass_gmail;
							$this->mail->From       = mail_gmail;              
							$this->mail->FromName   = 'INFO ' . XAT_NAME;
							$this->mail->Subject    = \Server::PrintMessage('login', 'logpin',[$user->username]);
							$this->mail->AltBody    = "";
							$this->mail->Body       = "";
							$this->mail->Body      .= \Server::PrintMessage('login', 'logpin2',[$user->username, METHOD.'//'.DOMAIN.'/login?Pin='.$PinCode, $user->username]);
							$this->mail->Body      .= \Server::PrintMessage('login', 'logfrom',[]) . implode(',',$userdetails) . "\n\n";
							$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'.DOMAIN.'/'. XAT_NAME, FACEBOOK]);
							$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
							$this->mail->AddAddress($user->email, "");
							$this->mail->IsHTML(false);
							$this->mail->Send();
							
						} 
						$Err['Err']['login'] = \Server::PrintResult('login','emcheck');
						break;
					}

					if ($Delete){
						if ($user->UsernameChangeTime > time()) {
							$Err['Err']['delete'] = \Server::PrintResult('login','del30') . $this->user->getDays($user->UsernameChangeTime) . \Server::PrintResult('buy','days') .' E20';
							break; 
						}
						if ($user->torched == 1) {
							$Err['Err']['delete'] = 'Account was torched';
							break;
						}
						if ($Pin || $user->pin != $Pin) {
							if (smtpmail == true) {
								$PinCode = rand(1, 10000000000);
								$this->user->updateData('users', ['pin' => $PinCode ], ['username' => $user->username]);
								$this->mail->IsSMTP();
								$this->mail->SMTPAuth   = true;
								$this->mail->SMTPSecure = SMTP_Sec;
								$this->mail->Host       = host_smtp;
								$this->mail->Port       = port_gmail;
								$this->mail->Username   = mail_gmail;
								$this->mail->Password   = pass_gmail;
								$this->mail->From       = mail_gmail;              
								$this->mail->FromName   = 'INFO ' . XAT_NAME;
								$this->mail->Subject    = \Server::PrintMessage('login', 'logpin',[$user->username]);
								$this->mail->AltBody    = "";
								$this->mail->Body       = "";
								$this->mail->Body      .= \Server::PrintMessage('login', 'logpin2',[$user->username, METHOD.'//'.DOMAIN.'/login?Pin='.$PinCode, $user->username]);
								$this->mail->Body      .= \Server::PrintMessage('login', 'logfrom',[]) . implode(',',$userdetails) . "\n\n";
								$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'.DOMAIN.'/'. XAT_NAME, FACEBOOK]);
								$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
								$this->mail->AddAddress($user->email, "");
								$this->mail->IsHTML(false);
								$this->mail->Send();
							}
						$Err['Err']['delete'] = \Server::PrintResult('login','delcheck');
						break;
						}
						$this->user->deleteData('ranks',['userid' => $user->id]);
						$this->user->deleteData('users',['id' => $user->id]);
						$this->user->InsertData('users',
								[
									'id'  => $user->id,
									'k'   => $user->k,
									'k2'  => $user->k2,
									'k3'  => $user->k3
								]
						);
					} else if ($ChangeUserName) {
						if ($user->UsernameChangeTime > time()) {
							$Err['Err']['newname'] = 'You cant change your username for '.$this->user->getDays($user->UsernameChangeTime).' days E17';
							break;
						}
						if (Validator::isNumeric(substr($Username, 0, 1))) {
							$Err['Err']['newname'] = \Server::PrintResult('buy','firstletter');
							break; 
						}
						if (strlen($Username) < 10) {
							$Err['Err']['newname'] = \Server::PrintResult('buy','short').' E47';
							$stop = 1;
							break; 
						}
						if (strlen($Username) > 18 || !ctype_alnum($Username) || $this->isBad($Username)) {
							$Err['Err']['newname'] = \Server::PrintResult('login','namebad');
							break; 
						}
						$CheckName = $this->user->getUserByUsername($Username);
						if ($CheckName) {
							$Err['Err']['newname'] = \Server::PrintResult('buy','nametaken');
							break; 	
						}
						$days = 14;
						$time = $this->user->makeDays($days);
						$this->user->updateData('users', ['UsernameChangeTime' => $time, 'username' => $Username], ['id' => $user->id]);
						$user = $this->user->getUserById($user->id);
					}
							
					if ($Protected && $Locked) {
						if ($Protected == 'ON' && $Locked == 'ON') {
							if($user->isp == $userdetails['isp'])
							$type_protection = 'ip';
						}				
						if ($Protected == 'OFF' && $Locked == 'OFF') {
							$type_protection = 'country';
							if (empty($user->country)) {
								$this->user->updateData('users', ['country' => $userdetails['country']], ['id' => $user->id]);
							}
						}				
						if ($Protected == 'ON' && $Locked == 'OFF') {
							$type_protection = 'isp';
							if (empty($user->isp)) {
								$this->user->updateData('users', ['isp' => $userdetails['isp']], ['id' => $user->id]);
							}
						}
						if ($user->protection != $type_protection && !empty($type_protection)) {
							$this->user->updateData('users', ['protection' => $type_protection], ['id' => $user->id]);
							if ($this->user->getDays($user->is_held) < 4) {
								$this->user->updateData('users', ['is_held' => $this->user->makeDays(3)], ['id' => $user->id]);
								$Err['Err']['settings'] = \Server::PrintResult('login','precaution');	
							}
						}
					}
					/*if (!empty($user->isp) && $user->isp != $userdetails['isp']) {
						$this->user->updateData('users', ['is_held' => $this->user->makeDays(7)], ['id' => $user->id]);
					}  
					if ($user->isp == $userdetails['isp'] && $this->user->getDays($user->is_held) > 3) {
						$this->user->updateData('users', ['is_held' => time()], ['id' => $user->id]);
					}*/
					if ($ResetApiKey && $ResetApiKey == 'ResetApiKey') {
						$this->user->updateData('users', ['apiKey' => $this->core->rand(20)], ['id' => $user->id]);
					}
					$user = $this->user->doLogin($user->username, $password);
					$Err['Err']['todo'] = 
							[
								'DeviceId'     => md5($user->connectedlast),
								'w_userno'     => (string) $user->id,
								'w_registered' => $user->username,	
								'PassHash'     => substr(sha1($user->password), 0, 20),
								'logintime'    => (string) time()
							];
					$Err['Err']['protect'] = $user->protection;
					if (!empty($user->apiKey)) {
						$Err['Err']['ApiKey']  = $user->apiKey;	
					}
					if (isset($_POST['DoneQuiz']) && $_POST['DoneQuiz'] == 1) {
						$this->user->updateData('users', ['AuthSelect' => 1], ['id' => $user->id]);
					}
					$GroupPowers = $this->user->getAssignedPowers($user->id);
					if ($GroupPowers) {
						$PowersBody .= "<h3 data-localize=login.grpassigns>Current group power assignments:</h3>\n\r";
						foreach ($GroupPowers as $gp) {
							$power         = $this->user->getPowerName($gp['power']);
							$PowersBody   .= $power->name.": <a href=//".DOMAIN."/{$gp['chat']}>{$gp['chat']}</a><br>";
						}
						$Err['Err']['PowerAssignments']  = $PowersBody;	
					}
					if ($user->is_held > time()) {
						$Err['Err']['held'] = 'Account held '. $this->user->getDays($user->is_held) .' days';	
					}
					$Err['Err']['Settings'] = $this->DoLogin($NameEmail, $password, 8);
					$Err['Err']['Settings2'] = '<div class="text-success font-weight-bold mb-3" data-localize="web.loginsuccess">You have been successfully logged in!</div>';
					//<iframe src="https://oxat.in/embed/chat.php#id=2&gn=" width="10" height="10" frameborder="0" scrolling="no"></iframe>
				break;
				case $ForgotPassword && $ForgotPassword == 1:
					if (!Validator::recaptcha($captcha)) {
						$Err['Err']['lost'] = \Server::PrintResult('main','recaperr');
						break;
					}
					if (!Validator::isValidEmail($NameEmail)) {
						$Err['Err']['lostemail'] = $NameEmail . \Server::PrintResult('main','evalid');
						break;
					}
					$user = $this->user->getUserEmail($NameEmail);
					if (!$user) {
						$Err['Err']['lostemail'] = \Server::PrintResult('buy','notfound');
						break;
					}
					if (smtpmail == true) {
						
						$forgotHash = $this->core->rand(10);
						$this->user->updateData('users', ['forgothash' => $forgotHash], ['id' => $user->id]);
						$this->mail->IsSMTP();
						$this->mail->SMTPAuth   = true;
						$this->mail->SMTPSecure = SMTP_Sec;
						$this->mail->Host       = host_smtp;
						$this->mail->Port       = port_gmail;
						$this->mail->Username   = mail_gmail;
						$this->mail->Password   = pass_gmail;
						$this->mail->From       = mail_gmail;              
						$this->mail->FromName   = 'INFO ' . XAT_NAME;
						$this->mail->Subject    = \Server::PrintMessage('login', 'chgpass1',[$user->username]);
						$this->mail->AltBody    = "";
						$this->mail->Body       = "";
						$this->mail->Body      .= \Server::PrintMessage('login', 'chgpass2',[$user->username, METHOD.'//'.DOMAIN.'/login?UserId='.$user->id.'&k2='.$user->k2.'&key='.$forgotHash.'&mob=0']);
						$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'.DOMAIN.'/'. XAT_NAME, FACEBOOK]);
						$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
						$this->mail->AddAddress($user->email, "");
						$this->mail->IsHTML(false);
						$this->mail->Send();
					}
					$Err['Err']['lostok'] =  \Server::PrintResult('login','chgpass3');
				break;
				case $ChangePassword && $ChangePassword == 1:	
					if (strlen($password) < 6) {
						$Err['Err']['cppass1'] =  \Server::PrintResult('login','passshort').' E39';
						break;
					}
					if (!Validator::isAlphanumeric($password)) {
						$Err['Err']['cppass1'] =  \Server::PrintResult('login','len6').' E39';
						break;
					}
					if ($key && $UserId && strlen($key) == 10) {
						$user = $this->user->getUserById($UserId);
						if (!$user) {
							$Err['Err']['changepass'] = \Server::PrintResult('login','notvalid').' E39';
							break;
						}
						if ($user->forgothash !== $key) {
							$Err['Err']['changepass'] = \Server::PrintResult('login','notvalid').' E39';
							break;
						}
						$this->user->updateData('users', ['password' => $this->core->hash($password), 'forgothash' => ''], ['id' => $user->id]);
						$Err['Err']['changepassok'] = \Server::PrintResult('login','passupdetd');
						break;
					}
					if (!Validator::isAlphanumeric($NameEmail)) {
						$Err['Err']['changepass'] = \Server::PrintResult('login','notvalid').' E15';
						break;
					}
					$user = $this->user->getUserByUsername($NameEmail);
					if (!$user) {
						$Err['Err']['changepass'] = \Server::PrintResult('login','notvalid').' E14';
						break;
					}
					if (!$this->core->validate($oldpassword, $user->password)) {
						$Err['Err']['changepass'] = \Server::PrintResult('login','notvalid').' E14';
						break;
					}
					$this->user->updateData('users', ['password' => $this->core->hash($password)], ['id' => $user->id]);
					$Err['Err']['changepassok'] = \Server::PrintResult('login','passupdetd');
				break;
				case $mode && $mode == 1:
				case $Register && $Register == 1:
					//if (!$this->user->checkMaxAccounts()) {
					//	$Err['Err']['login'] = 'You exceeded the maximum number of registrations allowed';
					//	break;
					//}
					$abc = 'register';
					$abcc = $this->user->disablepages($abc);
					if ($abcc->register == 0){
						$Err['Err']['login'] = 'Sorry not allowed you '.$abc.' this website';
						break;
					}
					if ($k2 && $UserId) {
						$user = $this->user->getUserById($UserId);
					}
					if (!$user) {
						$Err['Err']['login'] = $UserId .' '. \Server::PrintResult('login','nolonger').' E51';
						break;					
					}
					if ($user) {
						if ($user->confirmed == 1) {
							$Err['Err']['login'] = $user->id . \Server::PrintResult('login','regdup').' E4';
							break;
						}
						if ($user->k2 != $k2) {
							$Err['Err']['login'] = \Server::PrintResult('login','badid').' E67';
							break;
						}
						if ($ac && Validator::isAlphanumeric($ac) && $user->confirmed != 1) {
							if ($user->confirmed != $ac) {
								$Err['Err']['ShowRegister'] = (int) 1;
								$Err['Err']['register']     = $UserId . \Server::PrintResult('login','badid').' E50';
								$Err['Err']['regnoform']    = (int) 1;
								break;					
							}
							$this->user->updateData('users', ['confirmed' => 1], ['confirmed' => $ac]);
							$Err['Err']['todo'] = 
									[
										'DeviceId'     => md5($user->connectedlast),
										'PassHash'     => substr(sha1($user->password), 0, 20),
										'logintime'    => (string) time(),
										'w_registered' => $user->username,
										'w_userno'     => (string) $user->id
									];
							$Err['Err']['protect']  = $user->protection;
							$Err['Err']['Settings'] = $this->doLogin($user->username, $user->password);
							break;
						}
						
						$Err['Err']['ShowRegister'] = (int) 1;
		
						if ($Register) {
							$stop = 0;
							if (!Validator::recaptcha($captcha)) {
								$Err['Err']['registercap'] = \Server::PrintResult('main','recaperr');
								$stop = 1;
							}
							if (!$agree || ($agree && $agree !== 'ON')) { 	 
								$Err['Err']['registerterms'] = \Server::PrintResult('buy','terms');
								$stop = 1;
							}	
							if (strlen($Username) < 10) {
								$Err['Err']['registername'] = \Server::PrintResult('buy','short') . ' E47';
								$stop = 1;
							}
							if (strlen($Username) > 18  ||  !Validator::isAlphanumeric($Username)) {
								$Err['Err']['registername'] = \Server::PrintResult('login','namebad').' E47';
								$stop = 1;
							}
							if (Validator::isNumeric(substr($Username, 0, 1))) {
								$Err['Err']['registername'] = \Server::PrintResult('buy','firstletter');
								$stop = 1;
							}
							if ($this->isBad($Username)) {
								$Err['Err']['registername'] = $Username . \Server::PrintResult('buy','notallowed');
								$stop = 1;
							}
							if ($this->user->isAlreadyRegistered($Username)) {
								$Err['Err']['registername'] = \Server::PrintResult('login','namedup') . ' E6';
								$stop = 1;
							}
							if ($password != $password2) {
								$Err['Err']['regpass'] = \Server::PrintResult('login','passne') . ' E40';
								$stop = 1;
							}
							if (!Validator::isAlphanumeric($password)) {
								$Err['Err']['regpass'] = \Server::PrintResult('login','len6') . ' E65';
								$stop = 1;
							}					
							if (strlen($password) < 6) {
								$Err['Err']['regpass'] = \Server::PrintResult('login','passshort');
								$stop = 1;
							}
							if (!Validator::isValidEmail($email)) {
								$Err['Err']['regemail'] = $email . \Server::PrintResult('main','evalid') . ' E42';
								break;
							}
							$explode = explode('@', $email);
							if (!in_array($explode[1], ALLOW_EMAIL)) {
								$Err['Err']['regemail'] = $explode[1] . \Server::PrintResult('login','eblock');
								$stop = 1;
							}
							$getEmail = $this->user->getUserEmail($email);
							if ($getEmail) {
								$Err['Err']['regemail'] = \Server::PrintResult('login','emaildup') . ' E7';
								$stop = 1;
							}
							
							if ($stop == 1) { break; }
							
							$this->user->deleteData('users',['id' => $user->id, 'k2' => $user->k2]);
							$RegisterCode = $this->core->rand(10);
							$userdetails  = $this->core->userdetails($this->user->ipAddr());
							$this->user->doRegister($user->id, $user->k, $user->k2, $user->k3, $Username, $password, $email, $userdetails['isp'], $userdetails['country'], $RegisterCode);
							
							if (smtpmail == true) {	
							
								$this->mail->IsSMTP();
								$this->mail->SMTPAuth   = true;
								$this->mail->SMTPSecure = SMTP_Sec;
								$this->mail->Host       = host_smtp;
								$this->mail->Port       = port_gmail;
								$this->mail->Username   = mail_gmail;
								$this->mail->Password   = pass_gmail;
								$this->mail->From       = mail_gmail;              
								$this->mail->FromName   = 'INFO ' . XAT_NAME;
								$this->mail->Subject    = \Server::PrintMessage('login', 'activate1',[$Username]);
								$this->mail->AltBody    = "";
								$this->mail->Body       = "";
								$this->mail->Body      .= \Server::PrintMessage('login', 'activate2',[$Username, METHOD . '//' . DOMAIN .'/login?UserId='.$user->id.'&k2='.$user->k2.'&ac='.$RegisterCode.'&mode=1', $Username]);
								$this->mail->Body      .= \Server::PrintMessage('login', 'forhelp',[ METHOD . '//'. DOMAIN .'/'. XAT_NAME, FACEBOOK]);
								$this->mail->Body      .= \Server::PrintMessage('login', 'noreply',[]);
								$this->mail->AddAddress($email, "");
								$this->mail->IsHTML(false);
								$this->mail->Send();
								
							}
							
							$Err['Err']['captoken']   = "{$user->id},{$user->k},{$user->k3},";
							$Err['Err']['regdone']    = \Server::PrintResult('login','regdone');
							$Err['Err']['regnoform']  = (int) 1;
						}	
					}
				break;
			}
			break;
		}
		if (empty($juser) && empty($jpass) && empty($jemail)) {
			if ($jForgotPassword == "ResetPassword"){}else{
				return View::json($Err);
			}
		//return View::json($Err);
		}
	}
}