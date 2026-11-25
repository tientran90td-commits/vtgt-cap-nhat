'use strict';
/*
 * KỊCH BẢN LỜI THOẠI (sửa được ở bảng điều khiển -> mục "Lời thoại").
 * - Mỗi câu có thể có nhiều DÒNG: mỗi dòng là một cách nói, game luân phiên chọn cho đỡ lặp.
 * - Trong câu dùng {ten}, {qua}... là chỗ game tự điền (xem danh sách bên dưới).
 * - Lưu vào data/thoai.json. Xóa file đó hoặc bấm "Mặc định" để quay lại câu gốc.
 */
const fs = require('fs');
const path = require('path');

const SAMPLE = {
  ten: 'Minh Anh',
  ten1: 'Minh Anh',
  ten2: 'Tuấn Kiệt',
  tiep: 'Tuấn Kiệt',
  thua: 'Bích Trâm',
  oco: 'mã ăn f ba',
  diem: '30',
  giay: '25',
  qua: 'Hoa hồng',
  so: '3',
  lydo: 'hết giờ quá nhiều lần và bị xử thua',
  canhgioi: 'Trúc Cơ',
};

const VAR_HELP = {
  ten: 'tên người chính trong câu',
  ten1: 'tên người thứ nhất',
  ten2: 'tên người thứ hai',
  tiep: 'tên người đến lượt tiếp theo',
  thua: 'tên người thua',
  oco: 'nước đi, ví dụ "mã ăn f ba"',
  diem: 'số điểm (thưởng, hoặc điểm bị mất)',
  giay: 'số giây',
  qua: 'tên món quà',
  so: 'số lượng / số ván',
  lydo: 'lý do xử thua',
  canhgioi: 'tên cảnh giới (rank)',
};

// role: 'mc' = điều phối viên, 'ref' = trọng tài
const DEFAULTS = [
  { key: 'welcome', group: 'Mở đầu', role: 'mc', label: 'Chào mừng (vòng đầu tiên)', vars: ['giay'],
    text: 'Chào mừng các bạn đến với Cờ vua trực tiếp! Hãy bình luận, thả tim hoặc tặng quà để giành suất lên bàn đấu. Chỉ còn {giay} giây!\nXin chào cả nhà! Cờ vua trực tiếp bắt đầu rồi, bình luận, thả tim, tặng quà để giành ghế lên bàn đấu. Còn {giay} giây, nhanh tay kẻo hết chỗ!\nChào mừng các kỳ thủ, đại kiện tướng và cả những người chỉ biết đi tốt! Còn {giay} giây để giành suất lên bàn đấu!' },
  { key: 'lobbyStart', group: 'Mở đầu', role: 'mc', label: 'Bắt đầu vòng mới', vars: ['giay'],
    text: 'Vòng mới bắt đầu! Hãy bình luận, thả tim hoặc tặng quà để giành suất lên bàn đấu. Chỉ còn {giay} giây!\nVòng mới tới rồi! Hai ghế đang trống, ai bình luận, thả tim, tặng quà nhiều nhất là ngồi vào. Còn {giay} giây!\nBàn cờ đã dọn xong, quân đã lau bóng. Ai muốn lên bàn thì tương tác ngay, còn {giay} giây thôi!' },
  { key: 'howTo', group: 'Mở đầu', role: 'mc', label: 'Giải thích cách chơi (lúc chờ)', vars: [],
    text: 'Cách chơi rất dễ: khi đến lượt, người chơi bình luận nước đi, ví dụ e bốn, hoặc mã f ba. Chiếu hết vua đối phương là thắng. Muốn lên bàn đấu, hãy bình luận, thả tim và tặng quà!\nGõ ô quân đi tới, như e bốn, hoặc gõ tên quân rồi ô, như mã f ba. Chiếu hết là thắng. Bình luận nhiều, thả tim, tặng quà để được chọn lên bàn nhé!\nCách chơi dễ như ăn kẹo: tới lượt thì gõ nước đi như e bốn hoặc mã f ba. Chiếu hết là thắng, nhớ giữ vua thật an toàn nhé!\nĐến lượt mình thì bình luận nước đi, ví dụ tốt e bốn. Gõ nhầm quân thì không sao, thử lại là được!' },
  { key: 'greet', group: 'Mở đầu', role: 'mc', label: 'Chào người mới vào', vars: ['ten'],
    text: 'Chào {ten} đã ghé xem! Bình luận hoặc thả tim để giành suất chơi nhé.\nXin chào {ten}! Chúc bạn xem live vui vẻ, nhớ bình luận để được chọn lên bàn đấu nha.\nÔi, {ten} vừa tới! Bình luận để được chọn lên bàn đánh cờ nào!\nChào {ten}! Ngồi xuống xem cờ đi, biết đâu hôm nay chính bạn là vua!\nXin chào {ten}, bạn đến đúng lúc bàn cờ đang nóng!' },
  { key: 'lobbyWarn', group: 'Mở đầu', role: 'mc', label: 'Sắp hết giờ đua tương tác', vars: ['ten', 'ten1', 'ten2'],
    text: 'Còn mười giây! Đang dẫn đầu tương tác là {ten}.\nCòn mười giây thôi! {ten} đang dẫn đầu, ai muốn giành ghế thì nhanh tay lên!\nMười giây cuối cùng! {ten} đang cầm đầu bảng, các bạn ơi theo sát nhé!' },
  { key: 'lobbyEmpty', group: 'Mở đầu', role: 'mc', label: 'Chưa có ai lên bàn', vars: [],
    text: 'Chưa có ai lên bàn. Hãy bình luận hoặc thả tim để vào chơi nào!\nBàn cờ vắng hoe, quân cờ buồn ngủ cả rồi! Bình luận hoặc thả tim để vào chơi nào!\nChưa có ai lên bàn, vua trắng với vua đen đang ngồi nhìn nhau. Mau lên bàn đi các bạn!' },
  { key: 'pickedPair', group: 'Chọn người chơi', role: 'mc', label: 'Công bố 2 người chơi', vars: ['ten1', 'ten2'],
    text: 'Hai người chơi được chọn là {ten1} và {ten2}. Xin chúc mừng!\nHai kỳ thủ hôm nay là {ten1} và {ten2}! Xin cho một tràng pháo tay!\nCó rồi! {ten1} gặp {ten2}, trận này hứa hẹn nhiều bất ngờ!' },
  { key: 'pickedChamp', group: 'Chọn người chơi', role: 'mc', label: 'Người thắng ở lại, có người thách đấu', vars: ['ten1', 'ten2'],
    text: '{ten1} tiếp tục giữ bàn, và sẽ thách đấu với {ten2}.\n{ten1} còn đang giữ ngôi, và lần này gặp thách đấu từ {ten2}. Ai sẽ giữ được ghế đây?\n{ten2} dám thách đấu nhà vô địch {ten1}! Căng thẳng ngay từ đầu!' },
  { key: 'coinToss', group: 'Tung đồng xu', role: 'ref', label: 'Trọng tài tung đồng xu', vars: [],
    text: 'Trọng tài tung đồng xu!\nTrọng tài tung đồng xu, ai rút trúng thì cầm quân trắng!\nĐồng xu bay lên rồi, hồi hộp quá!' },
  { key: 'coinResult', group: 'Tung đồng xu', role: 'ref', label: 'Kết quả đồng xu', vars: ['ten1', 'ten2'],
    text: 'Kết quả: {ten1} cầm quân trắng, đi trước. {ten2} cầm quân đen.\nKết quả: {ten1} cầm quân trắng, đi trước. {ten2} cầm quân đen, đi sau nhưng chưa chắc thua đâu!\nĐồng xu đã phán: {ten1} cầm trắng, {ten2} cầm đen. Chúc hai bên đánh hay!' },
  { key: 'startGame', group: 'Trong ván', role: 'ref', label: 'Mời đi nước đầu tiên', vars: ['ten'],
    text: 'Mời {ten} đi nước đầu tiên!\nMời {ten} đi nước đầu tiên, nhớ đừng đi tốt cạnh!\nBắt đầu! {ten} đi trước, mời bạn!\nMời {ten} khai cuộc, chúc bạn có nước đi để đời!' },
  { key: 'move', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi + người kế tiếp', vars: ['ten', 'oco', 'tiep'],
    text: '{ten}: {oco}. Đến lượt {tiep}.\n{ten} đi {oco}. Đến lượt {tiep}.\n{ten} đi {oco}. Đến lượt {tiep}, nghĩ kỹ rồi hãy đi nhé!\n{ten}: {oco}. Mời {tiep}!' },
  { key: 'moveEnd', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi quyết định (cuối ván)', vars: ['ten', 'oco'],
    text: '{ten}: {oco}.\n{ten} đi {oco}. Hay quá!\n{ten}: {oco}. Quyết định rồi!' },
  { key: 'warn10', group: 'Trong ván', role: 'ref', label: 'Cảnh báo còn 10 giây', vars: ['ten'],
    text: '{ten} còn mười giây.\n{ten} ơi, còn mười giây thôi, đừng ngủ gật nữa!\n{ten} còn mười giây, quân cờ đang chờ đó!\nMười giây cuối của {ten}, mau đi một nước đi!' },
  { key: 'timeoutAuto', group: 'Trong ván', role: 'ref', label: 'Hết giờ, đánh thay', vars: ['ten', 'oco'],
    text: '{ten} hết giờ. Hệ thống đi thay: {oco}.\n{ten} ngủ quên mất rồi, hệ thống đi thay: {oco}. Lần sau đừng để quân cờ chờ lâu nhé!\n{ten} hết giờ, hệ thống nhanh tay đi giúp: {oco}.' },
  { key: 'winGame', group: 'Kết quả', role: 'ref', label: 'Có người thắng', vars: ['ten', 'thua', 'so'],
    text: 'Chiếu hết! {ten} chiến thắng.\nChiếu hết rồi! {ten} thắng thật xuất sắc!\nKết thúc! {ten} đại thắng, khí thế ngút trời!\nChiếu hết! {ten} thắng, {thua} đã hết nước đi an toàn!\nChiếu hết rồi! {ten} thắng, {thua} nhìn bàn cờ mà chưa hiểu chuyện gì xảy ra!\nVua của {thua} hết đường đi rồi! {ten} chiến thắng!' },
  { key: 'winForfeit', group: 'Kết quả', role: 'ref', label: 'Thắng do đối thủ bỏ cuộc / hết giờ', vars: ['ten', 'thua', 'lydo'],
    text: '{thua} {lydo}. {ten} giành chiến thắng, khí chất vượt trội hơn tất cả!\n{thua} {lydo}. {ten} thắng không cần đánh hết, đúng là thắng nhàn!\n{thua} {lydo}, {ten} ngồi yên mà vẫn thắng, may mắn hay bản lĩnh đây?' },
  { key: 'congrats', group: 'Kết quả', role: 'mc', label: 'Chúc mừng người thắng', vars: ['ten'],
    text: 'Xin chúc mừng {ten}! Quả là xuất sắc, khí chất lộ rõ!\nChúc mừng {ten}! Khí thế ngút trời, không ai theo kịp!\nBội phục {ten}! Thật xuất sắc, đúng là cao thủ cái thế!\n{ten} một nước định càn khôn, khí chất rạng ngời. Chúc mừng!\nChúc mừng {ten}! Nước đi này xứng đáng được in vào sách cờ vua!\nCung hỉ {ten}! Đối thủ còn đang ngồi tự hỏi mình sai ở đâu, còn bạn đã bay lên tiên!\nQuá xuất sắc! {ten} đi nước nào là đối thủ toát mồ hôi nước đó, chúc mừng!' },
  { key: 'streak', group: 'Kết quả', role: 'mc', label: 'Thắng liên tiếp', vars: ['ten', 'so'],
    text: '{ten} đã thắng {so} ván liên tiếp, xuất sắc vô song!\n{ten} thắng {so} ván liền không thua, chắc có bí kíp gia truyền! Ai biết xin chia sẻ nhé!\n{so} ván liên tiếp! {ten} ơi, có ai theo kịp bạn không, hay đi đâu hết rồi?' },
  { key: 'rankUp', group: 'Kết quả', role: 'mc', label: 'Người thắng đột phá cảnh giới (rank)', vars: ['ten', 'canhgioi'],
    text: 'Thiên địa dị tượng! {ten} đã đột phá, tiến nhập cảnh giới {canhgioi}, khung avatar thêm rực rỡ!\nChúc mừng {ten} đột phá thành công, bước vào cảnh giới {canhgioi}!\n{ten} đột phá lên {canhgioi}! Mây lành tụ hội, quân cờ cũng phải cúi chào, cung hỉ cung hỉ!\nChúc mừng {ten} lên {canhgioi}! Lên cấp nhanh như vậy chắc có uống đan dược trộm của sư phụ!\n{canhgioi}! {ten} đã bước vào cảnh giới mới, từ nay ra đường phải có người xách dép!' },
  { key: 'rankDown', group: 'Kết quả', role: 'mc', label: 'Người thua độ kiếp thất bại (mất hết điểm)', vars: ['ten', 'canhgioi', 'diem'],
    text: 'Mây đen kéo tới! {ten} độ kiếp thất bại, mất sạch {diem} điểm đạo hạnh! Xin chia buồn, hôm nay chưa hợp độ kiếp!\nĐộ kiếp thất bại! {ten} độ kiếp chưa thành, mất {diem} điểm đạo hạnh, về lại {canhgioi}! Buồn hơn cả lỡ đi nhầm quân lúc sắp chiếu hết!\n{ten} thua một ván, độ kiếp thất bại, {diem} điểm đạo hạnh bay theo mây khói! Không sao, ngã ở đâu đứng dậy ở đó!\nÔi không! Kiếp nạn lần này hơi khó, {ten} độ kiếp chưa thành, mất hết điểm, nay phải tu lại từ {canhgioi}! Tâm đừng loạn nhé!\nChia buồn cùng {ten}, độ kiếp thất bại, mất {diem} điểm rồi! Mau về bế quan luyện thêm, hoặc ăn đan dược vào cho khỏe!' },
  { key: 'loseComfort', group: 'Kết quả', role: 'mc', label: 'Động viên người thua (chưa có điểm để mất)', vars: ['thua'],
    text: '{thua} đừng buồn, thua keo này ta bày keo khác, đại kỳ thủ nào chẳng có lúc bị chiếu hết!\n{thua} thua rồi nhưng phong độ vẫn đẹp, đúng là thua mà không mất khí thế!\n{thua} cứ yên tâm, quân cờ thua chứ lòng người không thua, lần sau gỡ lại!\nThua một ván thôi mà, {thua} cứ uống chén trà cho tĩnh tâm, tu luyện lại là xong!' },
  { key: 'stepDown', group: 'Kết quả', role: 'mc', label: 'Đủ chuỗi thắng, nhường chỗ', vars: ['ten'],
    text: 'Đã đủ số ván liên tiếp, xin nhường chỗ cho người khác.\nThắng nhiều quá rồi, xin nhường bàn cho người khác thử sức nhé!\nĐủ chuỗi thắng rồi, xuống bàn nghỉ chút đi, để người khác còn có cơ hội thể hiện!' },
  { key: 'draw', group: 'Kết quả', role: 'ref', label: 'Hòa', vars: [],
    text: 'Ván đấu hòa!\nHòa! Hai bên đánh ngang tài ngang sức, không ai chịu nhường ai!\nHòa cờ! Hai vua nhìn nhau cười, bắt tay nhé!' },
  { key: 'hostReset', group: 'Khác', role: 'mc', label: 'Chủ phòng làm mới trận', vars: [],
    text: 'Chủ phòng đã làm mới trận đấu.\nChủ phòng làm mới bàn cờ, quân đã xếp lại, bắt đầu lại từ đầu!\nBàn cờ được làm mới, như chưa có chuyện gì xảy ra!' },
  { key: 'remindFollow', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc bấm follow', vars: ['diem'],
    text: 'Nếu bạn thấy vui, hãy bấm follow để không bỏ lỡ các buổi live sau nhé! Follow ngay được cộng {diem} điểm tương tác.\nBạn nào chưa follow thì bấm giúp mình một cái nha, được cộng {diem} điểm để giành suất lên bàn đấu!\nChưa follow thì bấm giúp mình một cái, cờ vua không có follow thì buồn lắm! Được cộng {diem} điểm đó!\nBấm follow đi các bạn, bấm xong được cộng {diem} điểm tương tác, vừa vui vừa có lợi!' },
  { key: 'remindShare', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc chia sẻ', vars: ['diem'],
    text: 'Chia sẻ buổi live này cho bạn bè để cùng vào đấu cờ nào! Chia sẻ được cộng {diem} điểm tương tác.\nMời thêm bạn bè vào xem và chơi cùng, chia sẻ live là được cộng {diem} điểm đó!\nRủ thêm bạn bè vào xem, chia sẻ live được cộng {diem} điểm, rủ càng đông bàn cờ càng vui!\nChia sẻ buổi live cho bạn bè xem cờ nào, được cộng {diem} điểm tương tác!' },
  { key: 'extraTime', group: 'Trong ván', role: 'ref', label: 'Người chơi xin thêm giờ', vars: ['ten', 'giay'],
    text: '{ten} xin thêm {giay} giây. Mời tiếp tục suy nghĩ!\n{ten} xin thêm {giay} giây, chắc đang tính nước đi để đời!\n{ten} cần thêm {giay} giây để nghĩ, mời suy nghĩ thoải mái!' },
  { key: 'confirmAsk', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 2 người thả tim xác nhận', vars: ['ten1', 'ten2', 'giay'],
    text: 'Xin mời {ten1} và {ten2} thả tim để xác nhận tham gia. Chỉ còn {giay} giây!\nMời {ten1} và {ten2} thả tim để xác nhận, không thả là mất ghế đó! Còn {giay} giây!\n{ten1}, {ten2} ơi, thả tim giữ ghế nào! Chỉ còn {giay} giây!' },
  { key: 'confirmAskOne', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 1 người thả tim xác nhận', vars: ['ten', 'giay'],
    text: 'Xin mời {ten} thả tim để xác nhận tham gia. Chỉ còn {giay} giây!\nMời {ten} thả tim xác nhận, thả tim cho vua trắng vui! Còn {giay} giây!\n{ten} ơi, thả tim một cái để giữ ghế nhé, còn {giay} giây!' },
  { key: 'confirmOk', group: 'Xác nhận thả tim', role: 'mc', label: 'Một người đã xác nhận', vars: ['ten'],
    text: '{ten} đã sẵn sàng!\n{ten} đã sẵn sàng, quân cờ đã sẵn sàng!\n{ten} thả tim rồi, tuyệt vời!' },
  { key: 'confirmWarn', group: 'Xác nhận thả tim', role: 'mc', label: 'Sắp hết giờ xác nhận', vars: ['ten', 'giay'],
    text: '{ten} ơi, thả tim ngay để giữ suất chơi, còn {giay} giây!\n{ten} ơi, còn {giay} giây, thả tim ngay kẻo mất ghế cho người khác!\n{ten}, nhanh tay thả tim đi, còn {giay} giây thôi!' },
  { key: 'confirmFail', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, mời người khác thay', vars: ['ten', 'ten2'],
    text: '{ten} chưa thả tim nên mất suất. Xin mời {ten2} thay thế, hãy thả tim để xác nhận nhé!\n{ten} chưa thả tim nên mất ghế rồi! Mời {ten2} lên thay, thả tim giữ ghế nhé!\n{ten} ngủ quên mất, ghế giờ thuộc về {ten2}, mời {ten2} thả tim xác nhận!' },
  { key: 'confirmFailNone', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, không còn ai thay', vars: ['ten'],
    text: '{ten} chưa thả tim nên mất suất. Chúng ta sẽ chọn lại người chơi nhé!\n{ten} không thả tim nên mất ghế. Chúng ta chọn lại người chơi nhé!\n{ten} mất ghế rồi, mời chọn lại!' },
  { key: 'giftThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn tặng quà', vars: ['ten', 'qua', 'so'],
    text: 'Cảm ơn {ten} đã tặng {qua}!\nCảm ơn bạn {ten} đã gửi tặng {qua}, thật tuyệt vời!\nWow, {ten} vừa tặng {qua}! Cảm ơn bạn nhiều nhé!\nCảm ơn {ten} đã tặng {qua}! Tim tôi đập nhanh hơn cả nước chiếu hết!\nÔi, {qua} từ {ten}! Cảm ơn bạn nhiều lắm!\n{ten} tặng {qua}, quả này hào phóng quá đi!' },
  { key: 'giftBig', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn quà LỚN', vars: ['ten', 'qua', 'so'],
    text: 'Wow! Cảm ơn {ten} đã tặng {qua}. Bạn thật hào phóng!\nÔi trời ơi, {qua} từ {ten}! Cảm ơn bạn rất nhiều!\nTrời ơi, {qua} từ {ten}! Hào phóng hơn cả nhà vô địch thế giới, cảm ơn bạn!\nWow wow wow! {ten} tặng {qua}, tôi suýt làm rơi cả quân hậu!' },
  { key: 'followThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn follow', vars: ['ten'],
    text: 'Cảm ơn {ten} đã follow!\nCảm ơn {ten} đã follow! Từ nay có thêm người xem cờ cùng rồi!\n{ten} vừa follow, chào mừng thành viên mới của hội cờ vua!' },
  { key: 'shareThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn chia sẻ LIVE', vars: ['ten'],
    text: 'Cảm ơn {ten} đã chia sẻ buổi LIVE!\nCảm ơn {ten} đã chia sẻ live, bạn tốt quá!\n{ten} chia sẻ live rồi, hội cờ vua sắp đông thêm rồi!' },
];

// Câu thoại cũ (do người dùng đã lưu) có yếu tố bạo lực sẽ bị bỏ qua, game dùng câu gốc mới thay thế
const VIOLENT = /sét đánh|thiên lôi|lôi kiếp|lôi đài|bá khí|bá đạo|mãnh hổ|báo thù|ăn hành|đánh cho|cắn quân|bắt nạt|chạy trốn|cướp ngôi|kiếm hiệp|luận võ|tan tác|cháy đen|thảm hại|dồn vào góc|chiến đấu|sấm sét/i;

class Script {
  constructor(file) {
    this.file = file;
    this.timer = null;
    this.items = new Map(DEFAULTS.map((d) => [d.key, { ...d, custom: null, enabled: true }]));
    this.counter = 0;
    if (!process.env.CARO_FAST) this.load();
  }

  load() {
    try {
      const saved = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      for (const [k, v] of Object.entries(saved)) {
        const it = this.items.get(k);
        if (!it || !v) continue;
        if (typeof v.text === 'string') {
          const kept = v.text.split('\n').filter((l) => !VIOLENT.test(l));
          it.custom = kept.length === v.text.split('\n').length ? v.text : kept.length ? kept.join('\n') : null;
        }
        if (typeof v.enabled === 'boolean') it.enabled = v.enabled;
      }
    } catch (e) {
      /* chưa có file */
    }
  }

  item(key) {
    return this.items.get(key);
  }

  textOf(key) {
    const it = this.items.get(key);
    if (!it) return '';
    return it.custom != null ? it.custom : it.text;
  }

  /** Điền chỗ trống và chọn 1 dòng. n = số thứ tự để luân phiên; trả về null nếu tắt / rỗng. */
  render(key, vars = {}, n = null) {
    const it = this.items.get(key);
    if (!it || !it.enabled) return null;
    const lines = this.textOf(key).split('\n').map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return null;
    const idx = n == null ? this.counter++ % lines.length : Math.abs(n) % lines.length;
    const out = lines[idx]
      .replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? '' : String(vars[k])))
      .replace(/\s+([.,!?])/g, '$1')
      .replace(/\s{2,}/g, ' ')
      .trim();
    return out || null;
  }

  set(key, { text, enabled }) {
    const it = this.items.get(key);
    if (!it) return false;
    if (typeof text === 'string') {
      const t = text.slice(0, 4000);
      it.custom = t.trim() === it.text.trim() ? null : t;
    }
    if (typeof enabled === 'boolean') it.enabled = enabled;
    this.save();
    return true;
  }

  reset(key) {
    const it = this.items.get(key);
    if (!it) return false;
    it.custom = null;
    it.enabled = true;
    this.save();
    return true;
  }

  resetAll() {
    for (const it of this.items.values()) {
      it.custom = null;
      it.enabled = true;
    }
    this.save();
  }

  list() {
    return [...this.items.values()].map((it) => ({
      key: it.key,
      group: it.group,
      role: it.role,
      label: it.label,
      vars: it.vars,
      text: it.custom != null ? it.custom : it.text,
      def: it.text,
      enabled: it.enabled,
      edited: it.custom != null,
    }));
  }

  save() {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      const out = {};
      for (const it of this.items.values()) {
        if (it.custom != null || !it.enabled) out[it.key] = { text: it.custom != null ? it.custom : it.text, enabled: it.enabled };
      }
      try {
        fs.mkdirSync(path.dirname(this.file), { recursive: true });
        fs.writeFileSync(this.file, JSON.stringify(out, null, 2));
      } catch (e) {
        /* không sao */
      }
    }, 600);
  }
}

module.exports = { Script, SAMPLE, VAR_HELP };
