<?php
namespace Classes;

use Vendor\Database;

class User {
	public $cn;
	protected $sql;
	protected $core;
	protected $mePower    = 349; // power ME id
	private $MAX_POWER = 24;

	public function __construct() {
		$this->cn = mt_rand();
		$this->sql = new Database();
		$this->core = new Core();
	}

	public function doLogin(string $user, string $pass) {
		$getUser = $this->sql->fetch_array('select * from users where username = \'' . $user . '\' limit 1;');
		if (empty($getUser[0])) {
			return false;
		} else if ($this->core->validate($pass, $getUser[0]['password'])) {
			$generateToken = md5(microtime(true));
			setcookie("user", $getUser[0]['username'], 2147483647, "/");
			setcookie("lc", $generateToken, 2147483647, "/");
			$this->sql->update('users', ['loginKey' => $generateToken , 'ip_login' => $this->ipAddr()], ['username' => $user]);
			return (object) $getUser[0];
		}
		return false;
	}

	public function doRegister(int $id, string $k, int $k2, int $k3, string $user, string $pass, string $email, string $isp, string $country, string $code) {
		$this->sql->insert('users', 
			[
				'id'            => $id,
				'username'      => $user,
				'password'      => $this->core->hash($pass),
				'nickname'      => base64_encode($user),
				'avatar'        => rand(1, 1759),
				'url'           => '',
				'k'             => $k,
				'k2'            => $k2,
				'k3'            => $k3,
				'xats'          => STARTING_XATS,
				'days'          => strtotime('+' . STARTING_DAYS . ' days'),
				'reserve'       => RESERVE_XATS,
				'email'         => $email,
				'enabled'       => '1',
				'connectedlast' => $this->ipAddr(),
				'ip_login' 		=> $this->ipAddr(),
				//'powers'        => $this->core->EncodePowers($this->loadAllPowers())[0],
				'isp'           => $isp,
				'country'       => $country,
				'confirmed'     => $code,
				'friends'       => '{}'
			]
		);
	}
	
	public function getXavis(): array {
		return $this->sql->fetch_array('select * from xavi;');
	}
	
	public function getEverypower(string $user) {
		$powers = $this->core->EncodePowers($this->loadAllPowers());
		return $this->update('users', ['powers' => $powers[0]]);
	}
	
	public function InsertData(string $table, array $parameters) {
		$this->sql->insert($table,$parameters);
	}

	public function doLogout(): bool {
		foreach ($_COOKIE as $k => $v) {
			setcookie($k, null, -1, "/");
		}
		return true;
	}
	
	public function doHtml5($user): array {
		$html5 = [
			'DeviceId'     => md5($user->connectedlast),
			'PassHash'     => substr(sha1($user->password), 0, 20),
			'w_registered' => $user->username,
			'w_userno'     => (string) $user->id,
			'TokenHash'    => '',
			'MobNo'        => '',
			'logintime'    => time()
		];
		return $html5;
	}

	public function isAuth(): bool {
		if (!array_key_exists('user', $_COOKIE) || !array_key_exists('lc', $_COOKIE)) {
			return false;
		}

		$username = strip_tags($_COOKIE['user']);
		$password = strip_tags($_COOKIE['lc']);
		$getUser  = $this->sql->fetch_array('select * from users where username = \'' . $username . '\' and loginKey = \'' . $password . '\' limit 1;');
		return !empty($getUser[0]);
	}

	public function ipAddr(): string {
		return array_key_exists("HTTP_CF_CONNECTING_IP", $_SERVER) 
			? $_SERVER["HTTP_CF_CONNECTING_IP"] 
			: $_SERVER['REMOTE_ADDR'];
	}
	
	public function getLastBan(int $id, int $chatid, string $special) {
		$getUser = $this->sql->fetch_array('select * from bans where userid = \'' . $id . '\' and chatid = \'' . $chatid . '\' and special = \'' . $special . '\' order by unbandate desc limit 1;');
		if (empty($getUser[0])) {
			return false;
		}
		return (object) $getUser[0];
	}
	
	public function get() {
		if (!$this->isAuth()) {
			return false;
		}
		$username = strip_tags($_COOKIE['user']);
		$password = strip_tags($_COOKIE['lc']);
		$getUser  = $this->sql->fetch_array('select * from users where username = \'' . $username . '\' and loginKey = \'' . $password . '\' limit 1;');
		if (empty($getUser[0])) {
			return false;
		}
		return (object) $getUser[0];
	}
	
	public function getUserById(int $id) {
		$getUser = $this->sql->fetch_array('select * from users where id = ' . $id . ' limit 1;');
		if (empty($getUser[0])) {
			return false;
		}
		return (object) $getUser[0];
	}
	public function update(array $values): bool {
		if (!$this->isAuth()) {
			return false;
		}
		$this->sql->update('users', $values, ['id' => $this->get()->id]);
		return true;
	}
	
	public function updateData(string $table, array $values, array $where): bool {
		$this->sql->update($table, $values, $where);
		return true;
	}
	
	public function deleteData(string $table, array $parameters): bool {
		$this->sql->delete($table, $parameters);
		return true;
	}	
	
	public function verifyPass(string $pass): bool {
		if (!$this->isAuth()) {
			return false;
		} else if ($this->core->validate($pass, $this->get()->password)) {
			return true;
		}
		return false;
	}
	
	public function getRankOnChat(int $id): int {
		if (!$this->isAuth()) {
			return false;
		}
		$getRank = $this->sql->fetch_array('select * from ranks where userid = \'' . $this->get()->id . '\' and chatid = \'' . $id . '\' limit 1;');
		if (empty($getRank[0])) {
			return false;
		}
		return $getRank[0]['f'];
	}

	public function getUserByK2(int $id, string $k2) {
		$getUser = $this->sql->fetch_array('select * from users where id = \'' . $id . '\' and k2 = \'' . $k2 . '\' order by id desc limit 1;');
		if (empty($getUser[0])) {
			return false;
		}
		return (object) $getUser[0];
	}
	
	public function getUserByUsername(string $username) {
		$getUser = $this->sql->fetch_array('select * from users where username = \'' . $username . '\' order by id desc limit 1;');
		if (empty($getUser[0])) {
			return false;
		}
		return (object) $getUser[0];
	}
	
	public function getUserEmail(string $email) {
		$getUserEmail = $this->sql->fetch_array('select * from users where email = \'' . $email . '\' order by id desc limit 1;');
		if (empty($getUserEmail[0])) {
			return false;
		}
		return (object) $getUserEmail[0];
	}
	
	public function getAuctionID(int $id, int $old) {
		$getAuctionID = $this->sql->fetch_array('select * from auction where uid = \'' . $id . '\' and old = \'' . $old . '\' and id != 1 limit 1;');
		if (empty($getAuctionID[0])) {
			return false;
		}
		return (object) $getAuctionID[0];
	}

	public function getAuctionConfig(int $old) {
		$getAuctionConfig = $this->sql->fetch_array('select * from auction where id = 1 limit 1;');
		$configuration = (array) json_decode($getAuctionConfig[0]['bidusername'], true);
		$configuration = ['start' => intval($configuration["p{$old}start"]), 'end' => intval($configuration["p{$old}end"])];
		return $configuration;
	}
	
	public function getPowerName(int $powerid) {
		$getPowerName = $this->sql->fetch_array('select * from powers where id = \'' . $powerid . '\' limit 1;');
		if (empty($getPowerName[0])) {
			return false;
		}
		return (object) $getPowerName[0];
	}

	public function getAuction(int $old): array {
		$getAuction = $this->sql->fetch_array('select * from auction where old = \'' . $old . '\' and id != 1;');
		return $getAuction;
	}
	
	public function disablepages(string $old) {
		$disablepages = $this->sql->fetch_array('select ' . $old . ' from systems;');
		return (object) $disablepages[0];
	}
	
	public function getAssignedPowers(int $id): array {
		$getAssignedPowers = [];
		$getAssignedPowers = $this->sql->fetch_array('select * from group_powers where assignedBy = \'' . $id . '\' ;');
		return $getAssignedPowers;
	}

	public function checkForID(int $id): bool {
		$getUser = $this->sql->fetch_array('select * from users where id = ' . $id . ' limit 1;');
		return !empty($getUser[0]);
	}

	public function newGuest() {
		$user     = new \stdClass();
		$user->k  = substr(sha1(microtime(true)), 0, 20);
		$user->k2 = rand(1000000, 999999999);
		$user->k3 = rand(1000000, 999999999);
		$this->sql->insert('users', 
			[
				'k'             => $user->k,
				'k2'            => $user->k2,
				'k3'            => $user->k3,
				'enabled'       => '1',
				'connectedlast' => $this->ipAddr(),
				'friends'       => '[]'
			]
		);
		$user->id = $this->sql->lastInsertId();
		return $user;
	}

	public function checkMaxAccounts(): bool {
		$getUser = $this->sql->fetch_array('select * from users where connectedlast = \'' . $this->ipAddr() . '\' and username != \'\';');
		return (count($getUser) < MAX_ACCOUNT);
	}

	public function getLastGuest() {
		$getUser = $this->sql->fetch_array('select * from users where connectedlast = \'' . $this->ipAddr() . '\' and username = \'\' or username is null order by id desc limit 1;');
		if (empty($getUser[0])) {
			return false;
		}
		return (object) $getUser[0];
	}

	public function isAlreadyRegistered(string $usr): bool {
		$getUser = $this->sql->fetch_array('select id from users where username = \'' . $usr . '\' limit 1;');
		return !empty($getUser[0]);
	}

	public function loadAllPowers(): array {
		$ignore = [0, 81, 95, 209]; // allpowers, everypower, xavi
		$getAll = $this->sql->fetch_array('select id from powers where everypower = 1;');
		$toInsert = [];
		foreach($getAll as $p) { 
			if(!in_array($p['id'], $ignore)) { 
				$toInsert[] = $p['id'];
			} 
		}
		return $toInsert;
	}

	public function hasMe(int $id): bool {
		$pid = $this->mePower;
		$getUser = $this->sql->fetch_array('select powers from users where id = ' . $id . ';');
		$powers = $this->core->DecodePowers($getUser[0]['powers']);
		if ($pid < 0) {
			$pid = abs($pid) + 640;
		}
		return array_key_exists($pid, $powers);
	}

	public function hasPower(int $pid): bool {
		if (!$this->isAuth()) {
			return false;
		}			
		$getUser = $this->sql->fetch_array('select powers from users where id = ' . $this->get()->id . ';');
		$powers = $this->core->DecodePowers($getUser[0]['powers']);
		if ($pid < 0) {
			$pid = abs($pid) + 640;
		}
		return array_key_exists($pid, $powers);
	}
	
	public function hasPower2(int $pid, int $userid): bool {			
		$getUser = $this->sql->fetch_array('select powers from users where id = ' . $userid . ';');
		if (!$getUser) {
			return false;
		}
		$powers = $this->core->DecodePowers($getUser[0]['powers']);
		if ($pid < 0) {
			$pid = abs($pid) + 640;
		}
		return array_key_exists($pid, $powers);
	}
	
	public function getDays(int $days) {
		return floor(($days - time()) / (24 * 3600) + 0.3) >= 1 ? floor(($days - time()) / (24 * 3600) + 0.3) : 0;
	}
	
	public function makeDays(int $days) {
		return floor($days * (3600 * 24)) + time();
	}
}