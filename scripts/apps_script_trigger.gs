// Google Apps Script (script.google.com, 프로젝트 "icn-air-deals 수집 트리거")에 둔 코드의 사본.
// GitHub Actions 예약 실행이 2~5시간 늦거나 빠져서(2026-10-25~29 기록), 수집 작업을 여기서 시각에 맞춰 건다.
// 수집이 끝나면 텔레그램 발송은 GitHub에서 이어서 돈다 (telegram.yml의 workflow_run).
// 설정: 프로젝트 시간대 서울, 스크립트 속성 GITHUB_TOKEN (fine-grained, icn-air-deals만, Actions 읽기·쓰기),
//       setupTriggers를 한 번 실행. 실패하면 구글이 실패 알림 메일을 보낸다 (토큰 만료 등)
var REPO = 'theddack/icn-air-deals';
var WORKFLOW = 'collect.yml';
var HOURS = [9, 13, 18, 22]; // KST, 각 시각 17분 전후(±15분)에 실행. 09·13·18시는 텔레그램 시간대 안

function dispatchCollect() {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('스크립트 속성 GITHUB_TOKEN이 없습니다');
  var res = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches',
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json'
      },
      payload: JSON.stringify({ ref: 'main' }),
      muteHttpExceptions: true
    }
  );
  // 성공은 204. 실패하면 오류를 던져서 구글이 실패 알림 메일을 보내게 한다
  if (res.getResponseCode() !== 204) {
    throw new Error('실행 요청 실패 ' + res.getResponseCode() + ': ' + res.getContentText());
  }
}

// 한 번만 실행. 다시 실행해도 기존 트리거를 지우고 새로 만들어서 중복되지 않는다
function setupTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'dispatchCollect') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  for (var j = 0; j < HOURS.length; j++) {
    ScriptApp.newTrigger('dispatchCollect')
      .timeBased().atHour(HOURS[j]).nearMinute(17).everyDays(1)
      .inTimezone('Asia/Seoul')
      .create();
  }
}
