'use strict';

let page;
let tab;
let todo;
let Pin;
let GotLogin;
let DoneQuiz;
let url = endPoints.register;
let loggedIn = !1;
document.body.style.backgroundColor = "white";
document.body.classList.remove("invisible");
$("#navGroup,#navxatApps").addClass("d-none");
Reset();
initConfig();
readUser();
setUser();
initLanguage();
initAuser3();
navClickHandlers();
startAnalyticsFour();
setLoggedin();
legacyLinks();
cookieBar();
localize(["web", "buy", "login", "mob1", "mob2", "quiz"]);
fetchPromo();
setLogo();
if (location.hash.includes("app=")) {
  $("#promoframe").addClass("d-none");
  $(".nav-tabs,.navbar-toggler,.pb-3").addClass("d-none");
  $("h1").addClass("d-none");
}
let Common = $("#CommonDiv").html();
$("#CommonDiv").html("");
$("#tablogin,#tablost,#tabchangename,#tabdelete,#tabdeletep,#tabgroup,#tabchangepass,#tablogout,#tabquiz").click(function (_0x33bc6c) {
  let _0xa0e65c = _0x33bc6c.currentTarget.id.substr(3);
  DoTask(_0xa0e65c);
  location.hash = "#!" + _0xa0e65c;
  return !1;
});
AddClicks();
Pin = xInt(GET.params.Pin);
let CheckReg;
let UserId = xInt(GET.params.UserId);
let k2 = xInt(GET.params.k2);
let mode = xInt(GET.params.mode);
let mobile = xInt(GET.params.mob);
function DoTask(_0x279d2a) {
  switch (_0x279d2a) {
    case "quiz":
      if (todo) {
        doQuiz();
        break;
      }
    case "lost":
      DoLost();
      break;
    case "logout":
      DoLogout();
      break;
    case "changepass":
      if (todo || GET.params.key) {
        DoChangePass();
        break;
      }
    case "changename":
      if (todo) {
        DoChangeName();
        break;
      }
    case "delete":
      if (todo) {
        DoDelete();
        break;
      }
    case "deletep":
      if (todo) {
        DoDeletep();
        break;
      }
    case "group":
      if (todo) {
        ShowDialog(_0x279d2a);
        break;
      }
    case "confirm":
      DoConfirm();
      break;
    default:
      _0x279d2a = "login";
      DoLogin();
  }
  SetTab(_0x279d2a);
}
function SetTab(_0x42631b) {
  if (_0x42631b) {
    page = _0x42631b;
  }
  $(".NavTabs").removeClass("active");
  $("#tab" + page).addClass("active");
  $("#lostemail").empty();
  if (GotLogin) {
    $("#loginlab").addClass("d-none");
    $("#settingslab").removeClass("d-none");
  } else {
    $("#loginlab").removeClass("d-none");
    $("#settingslab").addClass("d-none");
  }
}
function ShowDialog(_0x16ac3d) {
  $(".Dialog").addClass("d-none");
  $("#" + _0x16ac3d).removeClass("d-none");
}
function doQuiz() {
  ShowDialog("quiz");
}
function DoLogout() {
  $("#login").addClass("d-none");
  $("#logout,#tablogout").removeClass("d-none");
}
function DoConfirm() {
  Reset();
  let _0x3d8413 = getGET();
  let _0x2cbcad = $("#confirmerr");
  let _0x2e4366 = _0x3d8413.params.id;
  let _0x4cfef6 = _0x3d8413.params.tk;
  $("#login").addClass("d-none");
  $("#panel").addClass("d-none");
  $(".newnav").addClass("d-none");
  $("#confirm").removeClass("d-none");
  let _0x4fd5dd = "https://oxat.in/web_gear/chat/mlogin2.php?id=" + _0x2e4366 + "&tk=" + _0x4cfef6 + "&api=1";
  $.getJSON(_0x4fd5dd, function (_0x40fa38) {
    Maintenance(_0x40fa38);
    if (_0x40fa38.Err.loginok) {
      doSuccessMsg(_0x2cbcad, _0x40fa38.Err.loginok, false);
    } else if (_0x40fa38.Err.loginfail) {
      doErrorMsg(_0x2cbcad, _0x40fa38.Err.loginfail, false);
    } else if ("bad data" in _0x40fa38.Err && location.hash == "#!confirm") {
      doErrorMsg(_0x2cbcad, "<span>Please re-login from the mobile app</span>", false);
    } else {
      window.location.href = "https://oxat.in/login";
    }
  });
}
function DoDelete() {
  $(".Dialog").addClass("d-none");
  $("#delete").removeClass("d-none");
  $("#DeleteName,#DeleteName2,#DeleteNameBut").text(todo.w_registered);
  $("#orPerm").click(function (_0x1c734b) {
    $("#delPerm").removeClass("d-none");
    location.hash = "#!" + doRealHash(location.hash, "deletep");
    DoTask(getRealHash());
  });
}
function DoDeletep() {
  $(".Dialog").addClass("d-none");
  $("#deletep").removeClass("d-none");
  $("#DeleteName,#DeleteName2,#DeleteNameBut").text(todo.w_registered);
}
function DoChangeName() {
  ShowDialog("changename");
  $("#ChangeName").text(todo.w_registered);
}
function DoChangePass() {
  allErrsOff();
  ShowDialog("changepass");
  if (todo) {
    $("#cpname").val(todo.w_registered);
  }
  $("#cppass,#cppass1").val("");
  $("#cpform").removeClass("d-none");
}
function LoggedIn(_0x165ec7) {
  if (page != "logout") {
    if (_0x165ec7) {
      $("#LoginResult").html($("#LoginOk").html());
    } else {
      $("#LoginResult").html($("#LoginFailed").html());
    }
  } else {
    $("#LoginResult").html("");
  }
}
function DoSettings(_0x205e24) {
  let _0x1e784a = _0x205e24.Err;
  todo = _0x1e784a.todo;
  SetNewTodo(todo);
  if (location.href.includes("app=")) {
    let _0x341334 = window.location.href;
    _0x341334 = _0x341334.split("direct");
    window.location = _0x341334[0] + "box/embed.html?app=3";
    return;
  }
  if (_0x1e784a.Pin) {
    Pin = xInt(_0x1e784a.Pin);
  }
  $("#regname").text(todo.w_registered + " (" + todo.w_userno + ")");
  $("#pro" + _0x1e784a.protect).prop("checked", !0);
  $("#ApiKey").text(_0x1e784a.ApiKey);
  $("#PowerAssignments").html(_0x1e784a.PowerAssignments);
  if (_0x1e784a.PowerAssignments) {
    $("#tabgroup").removeClass("d-none");
    const _0x1af561 = $("#unassignallerr");
    document.querySelector("#unassignallbut")?.addEventListener("click", _0x5674dc => {
      _0x5674dc.preventDefault();
      allErrsOff();
      let _0x5bfe72 = document.querySelector("#iamsure");
      if (!_0x5bfe72 || !_0x5bfe72.checked) {
        doErrorMsg(_0x1af561, "<span data-localize=\"login.checkp\">You must check the box to proceed</span>", false, "login");
        return;
      }
      let _0xc5d311 = commonPost();
      _0xc5d311.NameEmail = _0xc5d311.YourEmail;
      _0xc5d311.Login = 1;
      _0xc5d311.SetUnAssignAll = 1;
      sendRequest(endPoints.register, _0xc5d311, "#unassignallbut", "unassignall", _0x221544 => {
        if (_0x221544.Err && Object.keys(_0x221544.Err).length > 0) {
          document.querySelector("#unassignallerr")?.classList?.remove("d-none");
          if (_0x221544.Err.gpnok) {
            doErrorMsg(_0x1af561, _0x221544.Err.gpnok, false, "login");
          } else if (_0x221544.Err.gpok) {
            $("#PowerAssignments").html("");
            $("#unassignhr").addClass("d-none");
            doSuccessMsg(_0x1af561, _0x221544.Err.gpok, false, "login");
          } else {
            DoErrs(_0x221544);
          }
        }
      });
    });
  } else {
    $("#tabgroup").addClass("d-none");
  }
  $("#closewin").html($("#closewin").html().replace("%s", "<br>"));
  $("#tabchangename,#tabdelete,#tabdeletep,#tabchangepass").removeClass("d-none");
  $("#tablost").addClass("d-none");
  GotLogin = 1;
  ShowDialog("settings");
  SetTab();
  if (_0x1e784a.settings && _0x1e784a.settings.indexOf(".k2sentemail") >= 0) {
    _0x205e24.Err.delsuccess = "<span data-localize=\"web.delsuc\">Account has been deleted</span>!";
    $("#embed").addClass("d-none");
  }
  DoErrs(_0x205e24);
  localize(["web"]);
}
function DoLogin() {
  $("#embed").empty();
  $("#tabregister").addClass("d-none");
  if (GotLogin) {
    ShowDialog("settings");
  } else {
    ShowDialog("login");
    let _0x4dfbb2 = $("#loginextra2");
    if (!_0x4dfbb2.html()) {
      _0x4dfbb2.html(Common);
      $("#username,#password").keypress(function (_0x49a7a6) {
        return DoReturn(_0x49a7a6);
      });
      $("#passviewbut").off("click").click(function (_0x9db307) {
        PassReveal($(_0x9db307.target));
      });
    }
  }
}
function DoReturn(_0x90172c) {
  return _0x90172c.which != 13 || ($("#lost").hasClass("d-none") ? $("#login").hasClass("d-none") ? $("#changename").hasClass("d-none") ? $("#changepass").hasClass("d-none") || $("#butchangepass").click() : $("#butchangename").click() : $("#butlogin").click() : $("#butlost").click(), !1);
}
function AddClicks() {
  $("#newname,#lostemail,#cpass1,#cpass2").keypress(function (_0x38685d) {
    return DoReturn(_0x38685d);
  });
  $(".PassReveal").click(function (_0x13be8b) {
    PassReveal($(_0x13be8b.target));
  });
  $("#butquiz").click(function (_0x977f47) {
    $("#tabquiz").removeClass("d-none");
    DoTask("quiz");
    loadQuiz();
  });
  $("#butlogin,#butsettings,#butchangename,#butdelete,#butdeletep,#butlost,#butregister,#butchangepass,#butlogout").click(function (_0x331e85) {
    _0x331e85.preventDefault();
    let _0x4d8557 = commonPost();
    _0x4d8557.NameEmail = _0x4d8557.YourEmail;
    if (Pin) {
      _0x4d8557.Pin = Pin;
    }
    if (todo) {
      _0x4d8557.UserId = todo.w_userno;
    }
    if (DoneQuiz) {
      _0x4d8557.DoneQuiz = 1;
    }
    if (!$("#settings").hasClass("d-none")) {
      switch ($("input[name='protection']:checked").val()) {
        case "1":
          _0x4d8557.Protected = "OFF";
          _0x4d8557.Locked = "OFF";
          break;
        case "2":
          _0x4d8557.Protected = "ON";
          _0x4d8557.Locked = "OFF";
          break;
        case "3":
          _0x4d8557.Protected = "ON";
          _0x4d8557.Locked = "ON";
      }
      if ($("#ResetApiKey").prop("checked")) {
        _0x4d8557.ResetApiKey = "ResetApiKey";
      }
      if ($("#DelMobs").prop("checked")) {
        _0x4d8557.DelMobs = "DelMobs";
      }
      loggedIn = !0;
    }
    if ($("#changepass").hasClass("d-none")) {
      if ($("#changename").hasClass("d-none")) {
        if ($("#delete").hasClass("d-none")) {
          if ($("#deletep").hasClass("d-none")) {
            if ($("#logout").hasClass("d-none")) {
              if ($("#lost").hasClass("d-none")) {
                if (CheckReg) {
                  CheckReg = 0;
                  _0x4d8557.UserId = UserId;
                  _0x4d8557.k2 = k2;
                  _0x4d8557.mode = 1;
                  if (mobile && mobile == 2) {
                    _0x4d8557.mob = 2;
                    _0x4d8557.k2 = "";
                  }
                  if (GET.params.ac) {
                    _0x4d8557.ac = GET.params.ac;
                  }
                } else if ($("#register").hasClass("d-none")) {
                  _0x4d8557.Login = 1;
                } else {
                  _0x4d8557.Register = 1;
                  _0x4d8557.UserId = UserId;
                  _0x4d8557.k2 = k2;
                  _0x4d8557.Username = $("#registername").val();
                  _0x4d8557["g-recaptcha-response"] = grecaptcha.getResponse();
                  _0x4d8557.agree = $("#registerterms").prop("checked") ? "ON" : 0;
                  _0x4d8557.password = $("#regpass").val();
                  _0x4d8557.password2 = $("#regpass2").val();
                  _0x4d8557.email = $("#regemail").val();
                  if (xConfig.captoken) {
                    _0x4d8557.captoken = xConfig.captoken;
                  }
                }
              } else {
                _0x4d8557.ForgotPassword = 1;
                _0x4d8557.NameEmail = $("#lostemail").val();
                _0x4d8557["g-recaptcha-response"] = grecaptcha.getResponse();
              }
            } else {
              _0x4d8557.Logout = 1;
            }
          } else {
            if (!$("#confirmdelete").is(":checked")) {
              doErrorMsg($("#deleteperr"), "<span data-localize=\"login.checkp\">You must check the box to proceed</span>", !1);
              return !1;
            }
            _0x4d8557.Delete = 1;
            _0x4d8557.Permanent = 1;
            _0x4d8557.Username = $("#newname").val();
            if ($("#DelMobs").prop("checked")) {
              _0x4d8557.DelMobs = "DelMobs";
            }
          }
        } else {
          _0x4d8557.Delete = 1;
          _0x4d8557.Username = $("#newname").val();
          if ($("#DelMobs").prop("checked")) {
            _0x4d8557.DelMobs = "DelMobs";
          }
        }
      } else {
        _0x4d8557.ChangeUserName = 1;
        _0x4d8557.Username = $("#newname").val();
      }
    } else {
      _0x4d8557.ChangePassword = 1;
      _0x4d8557.oldpassword = $("#cppass").val();
      _0x4d8557.NameEmail = $("#cpname").val();
      _0x4d8557.password = $("#cppass1").val();
      _0x4d8557.password2 = $("#cppass2").val();
      if (GET.params.key) {
        _0x4d8557.key = GET.params.key;
      }
      _0x4d8557.UserId = GET.params.UserId;
    }
    $(document.body).css({
      cursor: "wait"
    });
    urlPost(url, _0x4d8557).then(function (_0x2b7d76) {
      $(document.body).css({
        cursor: "default"
      });
      allErrsOff();
      $("#ResetApiKey").prop("checked", !1);
      $("#DelMobs").prop("checked", !1);
      Maintenance(_0x2b7d76);
      if (_0x2b7d76.Err.Settings) {
        DoSettings(_0x2b7d76);
        if (loggedIn) {
          $("#settingserr").removeClass("d-none");
          doSuccessMsg($("#settingserr"), "<span data-localize=\"web.updated\">Settings have been updated.</span>", true);
        }
      } else if (_0x2b7d76.Err.login && _0x2b7d76.Err.login.includes("login.mobok")) {
        doSuccessMsg($("#loginerr"), _0x2b7d76.Err.login, !1);
        DoLogin();
        $(".newnav").addClass("d-none");
        $("#loginextra").addClass("d-none");
        $("#loginHead").addClass("d-none");
      } else {
        if (_0x2b7d76.Err.login) {
          if (_0x2b7d76.Err.ClrHash && todo) {
            todo.PassHash = "1";
            SetNewTodo(todo);
          }
          GotLogin = 0;
          SetTab("login");
          $(".NotLogin").addClass("d-none");
          DoLogin();
        } else if (_0x2b7d76.Err.LogoutEmbed) {
          $("#Logout1").addClass("d-none");
          $("#Logout2").removeClass("d-none");
          localStorage.clear();
          clearCookies();
        } else if (_0x2b7d76.Err.deletep) {
          $("#formDeletep").addClass("d-none");
          doSuccessMsg($("#deletepsucc"), "<span data-localize=\"login.delpsuc\">An email has been sent to you for confirming the permenant deletion request.</span>", !1);
        } else {
          if (_0x2b7d76.Err.lostok) {
            "<p class=\"font-weight-bold\" data-localize=\"login.spambox\">IMPORTANT: If you do not receive an email check your spam inbox.</p>";
            "<span class=\"font-weight-bold\">(<span data-localize=\"login.minutesto\">The email could take up to 30 minutes to arrive.</span>)</span>";
            $("#lostextra").addClass("d-none");
            $("#lostcap").html("");
            doSuccessMsg($("#lostokerr"), "<p data-localize=\"login.emailsent\">An e-mail has been sent. Please click on the link in that email to set a new password.</p><p class=\"font-weight-bold\" data-localize=\"login.spambox\">IMPORTANT: If you do not receive an email check your spam inbox.</p><span class=\"font-weight-bold\">(<span data-localize=\"login.minutesto\">The email could take up to 30 minutes to arrive.</span>)</span>", false);
            return;
          }
          if (_0x2b7d76.Err.ShowRegister) {
            $("#id").val(UserId);
            SetTab("register");
            ShowDialog(page);
            $("[id^=\"tab\"]").addClass("d-none");
            $("#tabregister,#tablost,#tablogin").removeClass("d-none");
            if (_0x2b7d76.Err.regdone) {
              doSuccessMsg($("#regdoneerr"), _0x2b7d76.Err.regdone, false);
            }
            if (_0x2b7d76.Err.captoken) {
              xConfig.captoken = _0x2b7d76.Err.captoken;
              $("#registercap").addClass("d-none");
            } else {
              AddCap("registercap");
              xConfig.captoken = "";
            }
            if (_0x2b7d76.Err.regnoform) {
              $("#regform").addClass("d-none");
            }
          }
        }
        switch (page) {
          case "lost":
            if (!_0x2b7d76.Err.lostok) {
              AddCap("lostcap");
            }
            break;
          case "changepass":
            if (_0x2b7d76.Err.changepassok) {
              GotLogin = 0;
              SetTab();
              $("#cpform").addClass("d-none");
            }
        }
        if (!_0x2b7d76?.Err?.regdone) {
          DoErrs(_0x2b7d76);
        }
      }
      localize();
    });
  });
}
function DoLost() {
  Reset();
  ShowDialog("lost");
  AddCap("lostcap");
  $("#lostextra").removeClass("d-none");
}
function loadQuiz(_0x26b238) {
  if (_0x26b238 === undefined) {
    _0x26b238 = null;
  }
  _0x26b238 = _0x26b238 == null ? xConfig.lang : _0x26b238;
  urlPost("//oxat.in/json/translate/quiz-" + _0x26b238 + ".php").then(function (_0x16f6f3) {
    if (_0x16f6f3.quiz == null) {
      return loadQuiz("en");
    }
    var _0x49e94b = _0x16f6f3.quiz;
    var _0x2abfaa = null;
    var _0x56dd47 = [];
    var _0x5f2544 = 0;
    $.each(_0x49e94b, function (_0x5493c8, _0xa1609e) {
      if (isNaN(_0x5493c8.slice(-1)) || _0x5493c8.substr(0, 5) != "quizq" || _0x5493c8.indexOf("a") != -1) {
        if (_0x5493c8.substr(0, 5) == "quizq" && _0x5493c8.indexOf("a") > -1 && _0x5493c8.slice(-5) !== "image") {
          _0x56dd47[_0x2abfaa].answer.push([_0x5493c8, _0xa1609e].join(";"));
        } else if (_0x5493c8.substr(0, 5) == "quizq" && _0x5493c8.slice(-4) == "info") {
          _0x56dd47[_0x2abfaa].info = _0xa1609e;
        } else if (_0x5493c8.substr(0, 5) == "quizq" && _0x5493c8.slice(-5) == "image") {
          _0x56dd47[_0x2abfaa].image = _0xa1609e;
        }
      } else {
        _0x2abfaa = _0x5493c8.replace(/quizq/i, "");
        _0x5f2544++;
        _0x56dd47[_0x2abfaa] = {
          qID: parseInt(_0x2abfaa),
          question: _0xa1609e,
          answer: [],
          info: "",
          image: ""
        };
      }
    });
    $("#start_quiz").click(() => {
      $("#start_quiz").hide();
      $(".pro").removeClass("d-none");
      loadQuestions(_0x56dd47, 1, _0x5f2544);
    });
  });
}
function loadQuestions(_0x413e84, _0x995b81, _0x362dba) {
  var _0xf3fc97 = _0x413e84[_0x995b81];
  var _0x109355 = $("#quizForm");
  var _0x17e37b = $("#question_string");
  var _0x1c2d47 = $("#answers_list");
  var _0x1b9d7d = $("#question_image");
  var _0x5876b0 = $("#next");
  var _0xdbd49a = {
    Err: {}
  };
  var _0x21aae1 = !1;
  var _0x4f4b3f = 10;
  var _0x56c9cd = $(".mainCountdown");
  var _0x4d6b6e = !1;
  if (_0x995b81 > _0x362dba) {
    updateProgress(_0x995b81, _0x362dba);
    _0x4d6b6e = !0;
    _0x21aae1 = !0;
    _0x109355.hide();
    _0xdbd49a.Err.successmessage = "<span data-localize=\"quiz.gratz\">Congratulations, you have completed the quiz! You should now be more knowledgeable about safety on xat.</span>";
    _0xdbd49a.Err.waitmessage = "<span data-localize=\"quiz.redirect\">Please wait while you are redirected to the login page.</span>";
    DoErrs(_0xdbd49a);
    localize(["quiz"]);
    _0xdbd49a = {
      Err: {}
    };
    // TOLOOK
    setTimeout(() => {
      DoneQuiz = true;
      SetTab("login");
      $("#butsettings").click();
      resetQuiz(_0x362dba, _0x109355);
    }, 5000);
  } else {
    _0x17e37b.html(_0xf3fc97.question);
    if (_0xf3fc97.image != "") {
      _0x1b9d7d.html(_0xf3fc97.image.replace("<br ", "<"));
    }
    var _0x53d0ab = "";
    _0xf3fc97.answer = shuffleArray(_0xf3fc97.answer);
    for (var _0x5bb182 in _0xf3fc97.answer) {
      var _0x5a613c = _0xf3fc97.answer[_0x5bb182].split(";");
      _0x53d0ab += "<div class=\"form-check\">\n               <input class=\"form-check-input position-static\" type=\"radio\" id=\"" + _0x5a613c[0] + "\" name=\"qAnswer_" + _0xf3fc97.qID + "\" value=\"" + _0x5a613c[0] + "\">\n               <label class=\"form-check-label\" for=\"" + _0x5a613c[0] + "\">" + _0x5a613c[1] + "</label>\n         </div>";
    }
    _0x53d0ab += "</div>";
    _0x1c2d47.html(_0x53d0ab);
    if (_0x109355.hasClass("d-none")) {
      _0x109355.removeClass("d-none");
    } else {
      _0x109355.show();
    }
    $("input[type=radio]").change(_0x3c0309 => {
      if (_0x21aae1 == 0 && _0x4d6b6e == 0) {
        allErrsOff();
        var _0xf7bc69 = _0x3c0309.target.id;
        var _0x4eeebb = parseInt(_0xf7bc69.split("a")[1]);
        if (_0x4eeebb % _0x362dba < 1 || _0x4eeebb % _0x362dba > 1) {
          _0xdbd49a.Err.wronganswer = "<span data-localize=\"quiz.wronganswer\">This is incorrect. Please try again.</span>";
        } else {
          disableAnswers();
          if (_0xf3fc97.info != "") {
            _0xdbd49a.Err.moreinfo = "<span>" + _0xf3fc97.info + "</span>";
          }
          $("#countdown").html(_0x4f4b3f);
          var _0x32ada2 = // TOLOOK
          setInterval(() => {
            if (_0x4f4b3f == 10) {
              _0x56c9cd.removeClass("d-none");
            } else if (_0x4f4b3f == 0) {
              clearInterval(_0x32ada2);
              _0x995b81++;
              _0x21aae1 = true;
              _0x56c9cd.addClass("d-none");
              $("#countdown").html(10);
              _0x5876b0.removeClass("d-none");
              _0x5876b0.prop("disabled", false);
            } else {
              $("#countdown").html("" + _0x4f4b3f);
            }
            _0x4f4b3f--;
          }, 1000);
        }
        DoErrs(_0xdbd49a);
        localize(["quiz"]);
        _0xdbd49a = {
          Err: {}
        };
      }
    });
    _0x5876b0.click(() => {
      allErrsOff();
      if (_0x21aae1 != 0) {
        loadQuestions(_0x413e84, _0x995b81, _0x362dba);
        updateProgress(_0x995b81 - 1, _0x362dba);
        _0x21aae1 = false;
        _0x5876b0.addClass("d-none");
        _0x5876b0.prop("disabled", true);
      }
    });
  }
}
function updateProgress(_0xb81d50, _0x19a455) {
  var _0x5551e1 = $("#progress");
  var _0x4190b4 = Math.round(_0xb81d50 / _0x19a455 * 100);
  _0x5551e1[0].style.cssText = "width: " + _0x4190b4 + "%";
  _0x5551e1.html(_0x4190b4 + "%");
  _0x5551e1.attr("aria-valuenow", _0x4190b4);
}
function disableAnswers() {
  $(".mainForm input[type=radio]").each(function () {
    $(this).attr("disabled", !0);
  });
}
function resetQuiz(_0x1f8656, _0x25f924) {
  updateProgress(0, _0x1f8656);
  _0x25f924.hide();
  $(".pro").addClass("d-none");
  $("#start_quiz").show();
}
if (mode == 1) {
  if (!UserId) {
    UserId = xConfig.id;
  }
  if (!k2) {
    k2 = xConfig.k2;
  }
}
if (UserId && k2 && GET.params.key) {
  DoTask("changepass");
  $("#cpnouser").addClass("d-none");
} else if (UserId && k2 && (mode == 1 || GET.params.ac)) {
  CheckReg = 1;
  $("#butlogin").click();
} else {
  DoTask(getRealHash());
}