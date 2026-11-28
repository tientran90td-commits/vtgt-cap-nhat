'use strict';
/*
 * KỊCH BẢN LỜI THOẠI (sửa được ở bảng điều khiển -> mục "Lời thoại").
 * - Mỗi câu có thể có nhiều DÒNG: mỗi dòng là một cách nói, game luân phiên chọn cho đỡ lặp.
 * - Trong câu dùng {ten}, {qua}... là chỗ game tự điền (xem danh sách bên dưới).
 * - Lưu vào data/thoai.json. Xóa file đó hoặc bấm "Mặc định" để quay lại câu gốc.
 */
const fs = require('fs');
const { checkLine } = require('./safety');
const path = require('path');

const SAMPLE = {
  ten: 'Minh Anh',
  ten1: 'Minh Anh',
  ten2: 'Tuấn Kiệt',
  tiep: 'Tuấn Kiệt',
  thua: 'Bích Trâm',
  oco: 'ca 6',
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
  oco: 'ô cờ, ví dụ "ca 6"',
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
    text: 'Hoan nghênh chư vị đạo hữu giá lâm Caro Tiên Giới! Chư vị hãy bình luận hoặc thả tim để tham gia, hai vị được chọn sẽ lên đài thi đấu. Chỉ còn {giay} giây!\nChào mừng chư vị đến Caro Tiên Giới! Nơi đây không bán đan dược, chỉ bán sự căng thẳng! Bình luận, thả tim để lên đài, chỉ còn {giay} giây!\nĐệ tử mới đến cứ bình luận làm quen trước, hỏi han sau! Tại hạ hứa hiền lành, chỉ thích ngắm quân cờ. Còn {giay} giây nữa chọn người lên đài!\nCaro Tiên Giới khai mở! Ai thắng thì thành tiên, ai thua thì về tu luyện lại. Chỉ còn {giay} giây nữa là chọn người lên đài!' },
  { key: 'lobbyStart', group: 'Mở đầu', role: 'mc', label: 'Bắt đầu vòng mới', vars: ['giay'],
    text: 'Một vòng tranh đài mới đã mở! Chư vị đạo hữu hãy bình luận hoặc thả tim để tham gia. Chỉ còn {giay} giây!\nVòng mới tới rồi! Ai muốn thử sức thì gõ vài câu bình luận nhé, còn {giay} giây nữa thôi!\nĐài thi đấu mở cửa, đạo hữu nào muốn lên? Còn {giay} giây nữa!\nMột vòng tranh đài nữa! Ai muốn lên đài thì bình luận nhé, còn {giay} giây!' },
  { key: 'farmStart', group: 'Mở đầu', role: 'mc', label: 'Bắt đầu cày điểm sau trận (chế độ cày điểm)', vars: ['giay'],
    text: 'Trận đấu đã xong! Bắt đầu cày điểm, chư vị có {giay} giây. Hãy bình luận, thả tim, chia sẻ để lên bảng cơ duyên, người đứng đầu sẽ lên đài!\nKhoảng cày điểm đã mở, {giay} giây! Đạo hữu nào muốn lên đài thì bình luận, thả tim ngay nhé!\nVòng cày điểm bắt đầu! Trong {giay} giây, ai tương tác nhiều nhất sẽ được mời lên đài!' },
  { key: 'howTo', group: 'Mở đầu', role: 'mc', label: 'Giải thích cách chơi (lúc chờ)', vars: [],
    text: 'Quy củ rất đơn giản: đến lượt mình, đạo hữu hãy bình luận tọa độ, ví dụ j chín, để đặt quân. Ai kết được năm quân liền một đường là thắng. Muốn lên đài, chư vị hãy bình luận và thả tim!\nPháp môn rất dễ: gõ cột và hàng, như ca sáu, để đặt quân. Năm quân nối liền là đại thắng, kể cả bị chặn hai đầu. Bình luận và thả tim để có cơ hội được chọn lên đài nhé, chư vị đạo hữu!\nCách chơi dễ như ăn cháo: gõ cột và hàng, ví dụ j chín, là xong. Còn ai gõ nhầm thì thiên đạo cũng không cứu nổi đâu!\nNhớ nhé: năm quân thẳng hàng là thắng, bốn quân thì chưa, ba quân thì về nhà ngủ đi! Muốn lên đài thì bình luận và thả tim nhé!' },
  { key: 'greet', group: 'Mở đầu', role: 'mc', label: 'Chào người mới vào', vars: ['ten'],
    text: 'Hoan nghênh đạo hữu {ten} ghé thăm! Hãy bình luận để cùng tham gia nhé.\nBái kiến đạo hữu {ten}! Chúc đạo hữu tiêu dao thưởng lãm, bình luận để có cơ hội lên đài nha.\nÔi, đạo hữu {ten} ghé thăm! Ngồi xuống uống chén trà, rồi bình luận cho vui nhé!\nBái kiến đạo hữu {ten}! Nghe nói đạo hữu cờ rất cao thâm, hôm nay cho tại hạ chiêm ngưỡng xem sao!\nChào đạo hữu {ten}! Cửa tiên giới mở rộng, đạo hữu cứ bình luận vài chữ cho vui nhé!' },
  { key: 'lobbyWarn', group: 'Mở đầu', role: 'mc', label: 'Sắp hết giờ đua tương tác', vars: ['ten', 'ten1', 'ten2'],
    text: 'Còn mười giây nữa! Đạo hữu {ten} đang dẫn đầu bảng tương tác.\nCòn mười giây! Đạo hữu {ten} đang dẫn đầu, các vị khác cũng có thể tham gia nhé!\nMười giây cuối! Đạo hữu {ten} đang dẫn đầu bảng, ai muốn tham gia thì bình luận ngay bây giờ nhé!\nSắp hết giờ rồi! Đạo hữu {ten} đang dẫn đầu, ai muốn tham gia thì bình luận nhé!' },
  { key: 'lobbyEmpty', group: 'Mở đầu', role: 'mc', label: 'Chưa có ai lên bàn', vars: [],
    text: 'Trên đài chưa có đạo hữu nào. Mời chư vị bình luận để cùng thi đấu!\nTrên đài vắng như chùa bà đanh! Chư vị đạo hữu ai muốn chơi thì bình luận một câu nhé!\nChưa có ai lên đài, ai muốn chơi thì bình luận nhé!' },
  { key: 'pickedPair', group: 'Chọn người chơi', role: 'mc', label: 'Công bố 2 người chơi', vars: ['ten1', 'ten2'],
    text: 'Hai vị đạo hữu được chọn lên đài là {ten1} và {ten2}. Xin chúc mừng!\nĐài thi đấu đã có chủ: {ten1} gặp {ten2}! Hai cao thủ ngang tài ngang sức, xem ai hơn ai!\nHai vị đạo hữu {ten1} và {ten2} lên đài! Xin chư vị chuẩn bị hạt dưa nước ngọt, trò hay sắp bắt đầu!\nMời {ten1} và {ten2} bước lên đài thi đấu! Nhớ đừng run tay, quân cờ hiền lắm!' },
  { key: 'pickedChamp', group: 'Chọn người chơi', role: 'mc', label: 'Người thắng ở lại, có người thách đấu', vars: ['ten1', 'ten2'],
    text: 'Đạo hữu {ten1} tiếp tục giữ đài thi đấu, và sẽ tỷ thí cùng đạo hữu {ten2}.\nĐạo hữu {ten1} vẫn ngồi vững trên đài, chưa chịu đi! Hôm nay đạo hữu {ten2} liệu có giành được ghế không?\nLại là {ten1} giữ đài! Đạo hữu {ten2} bước lên, hy vọng ván này đánh thật hay!' },
  { key: 'coinToss', group: 'Tung đồng xu', role: 'ref', label: 'Trọng tài tung đồng xu', vars: [],
    text: 'Tại hạ xin tung đồng xu để định tiên cơ!\nTại hạ tung đồng xu đây! Xin thiên đạo phù hộ, đừng cho nó rơi xuống cống!\nĐồng xu bay lên rồi! Ai may mắn thì đi trước, ai xui thì đi sau, không sao đâu!' },
  { key: 'coinResult', group: 'Tung đồng xu', role: 'ref', label: 'Kết quả đồng xu', vars: ['ten1', 'ten2'],
    text: 'Kết quả: đạo hữu {ten1} đi trước, cầm quân X đỏ. Đạo hữu {ten2} cầm quân O xanh.\nĐồng xu đã nói: {ten1} đi trước, cầm quân X đỏ. {ten2} cầm quân O xanh, đừng khóc nhé!\n{ten1} trúng tiên cơ, cầm quân X đỏ! {ten2} cầm quân O xanh, hơi thiệt một chút nhưng đừng buồn!' },
  { key: 'startGame', group: 'Trong ván', role: 'ref', label: 'Mời đi nước đầu tiên', vars: ['ten'],
    text: 'Mời đạo hữu {ten} xuất chiêu đầu tiên!\nMời đạo hữu {ten} xuất chiêu đầu tiên, xin đừng đặt quân ở ngoài bàn cờ nhé!\nĐạo hữu {ten} khai cuộc đi! Đi nước nào cũng được, miễn là đừng đặt vào ô đã có quân!' },
  { key: 'move', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi + người kế tiếp', vars: ['ten', 'oco', 'tiep'],
    text: 'Đạo hữu {ten} xuất chiêu tại {oco}. Đến lượt đạo hữu {tiep}.\nĐạo hữu {ten} bố trận ở ô {oco}. Mời đạo hữu {tiep}.\nĐạo hữu {ten} đặt quân tại {oco}. Đạo hữu {tiep}, mời xuất chiêu.\nĐạo hữu {ten} ra chiêu tại {oco}! Đạo hữu {tiep}, đỡ được chiêu này không đây?\n{oco}! Đạo hữu {ten} đặt quân tự tin như thể đã nghĩ ba ngày ba đêm. Mời đạo hữu {tiep}!\nChiêu {oco} của đạo hữu {ten}, nhìn qua thì bình thường, nhìn lại vẫn bình thường! Mời {tiep} xuất chiêu.\nĐạo hữu {ten} đánh {oco}, tiếng bước chân đã vang vọng! Đạo hữu {tiep}, mời đạo hữu.\nÔi, {oco}! Chắc là ngón nghề gia truyền của đạo hữu {ten}. Đạo hữu {tiep}, đến lượt rồi!\nQuân cờ rơi xuống {oco}, thiên địa chấn động, ít nhất là chấn động nội tâm của {tiep}! Mời đạo hữu.' },
  { key: 'moveEnd', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi quyết định (cuối ván)', vars: ['ten', 'oco'],
    text: 'Đạo hữu {ten} xuất chiêu tại {oco}.\nĐạo hữu {ten} đánh {oco}, chiêu cuối cùng rồi đó!\n{oco}! Một nước cờ mà thiên địa đổi màu, đạo hữu {ten} đã ra chiêu quyết định!' },
  { key: 'occupied', group: 'Trong ván', role: 'ref', label: 'Ô đã có quân', vars: ['ten', 'oco'],
    text: 'Ô {oco} đã có quân rồi. Mời đạo hữu {ten} chọn ô khác.\nÔ {oco} có quân rồi, đạo hữu {ten} ơi! Đặt chồng lên là phạm luật đó, mắt nhìn kỹ lại chút!\nƠ kìa đạo hữu {ten}, ô {oco} có người ngồi rồi! Chọn ô khác đi, đừng chen chúc!' },
  { key: 'forbidden', group: 'Trong ván', role: 'ref', label: 'Đánh vào ô cấm (luật cấm)', vars: ['ten', 'oco', 'lydo'],
    text: 'Ô {oco} là ô cấm! Đạo hữu {ten} đi trước nên không được {lydo}. Mời chọn ô khác.\nKhoan đã đạo hữu {ten}, ô {oco} bị cấm vì {lydo}! Đi trước thì phải chịu luật cấm, chọn ô khác nhé!\nÔ {oco} không được đâu đạo hữu {ten}, {lydo} là phạm luật cấm đó!' },
  { key: 'banAsk', group: 'Trong ván', role: 'ref', label: 'Luật O cấm ô: mời O chọn ô cấm', vars: ['ten'],
    text: 'Quân X đã đi xong. Mời đạo hữu {ten} chọn một ô để cấm, gõ tọa độ ô đó.\nĐạo hữu {ten} có quyền cấm một ô! Gõ tọa độ ô muốn cấm, cả hai bên sẽ không được đặt quân vào đó đến hết ván.\nĐến lượt đạo hữu {ten} ra lệnh cấm một ô. Chọn khéo nhé, cấm là cấm đến hết ván đó!' },
  { key: 'banSet', group: 'Trong ván', role: 'ref', label: 'Luật O cấm ô: đã cấm xong', vars: ['ten', 'ten2', 'oco'],
    text: 'Ô {oco} đã bị cấm! Cả hai bên đều không được đánh vào đó nữa. Mời đạo hữu {ten} đi quân.\nĐạo hữu {ten} cấm ô {oco}! Cả hai bên nhớ tránh ô đó nhé. Mời đạo hữu {ten} xuất chiêu.\nÔ {oco} thành cấm địa rồi! Ai bước vào cũng phạm luật. Đạo hữu {ten}, mời đi quân!' },
  { key: 'banHit', group: 'Trong ván', role: 'ref', label: 'Luật O cấm ô: đánh vào ô bị cấm', vars: ['ten', 'oco'],
    text: 'Ô {oco} là cấm địa, cả hai bên đều không được đi! Đạo hữu {ten} chọn ô khác nhé.\nKhoan đã đạo hữu {ten}, ô {oco} bị cấm đến hết ván rồi! Chọn ô khác đi.\nĐạo hữu {ten} ơi, ô {oco} không đi được đâu, đã bị cấm rồi!' },
  { key: 'warn10', group: 'Trong ván', role: 'ref', label: 'Cảnh báo còn 10 giây', vars: ['ten'],
    text: 'Đạo hữu {ten}, chỉ còn mười giây, mau suy diễn!\nĐạo hữu {ten} ơi, mười giây thôi đó! Nghĩ nhanh lên, kẻo đồng hồ làm thịt bây giờ!\nCòn mười giây! Đạo hữu {ten} nghĩ kỹ chưa, hay đang ngủ gật?\nMười giây nữa là hết giờ rồi đạo hữu {ten}! Tim tại hạ còn đập nhanh hơn đạo hữu nghĩ đó!' },
  { key: 'timeoutAuto', group: 'Trong ván', role: 'ref', label: 'Hết giờ, đánh thay', vars: ['ten', 'oco'],
    text: 'Đạo hữu {ten} đã hết thời gian. Thiên đạo đánh thay vào ô {oco}.\nĐạo hữu {ten} nghĩ lâu quá, thiên đạo đành đánh thay vào {oco}! Dở thì đừng trách thiên đạo nhé!\nHết giờ rồi! Thiên đạo thay đạo hữu {ten} đánh {oco}. Hy vọng thiên đạo cờ cao hơn đạo hữu!' },
  { key: 'winGame', group: 'Kết quả', role: 'ref', label: 'Có người thắng', vars: ['ten', 'thua', 'so'],
    text: 'Trận tỷ thí kết thúc! Đạo hữu {ten} kết thành năm quân liền một đường, đại thắng!\nKết thúc rồi! Đạo hữu {ten} một nước hay, năm quân liền một đường, xuất sắc vô song!\nNăm quân đã thành hàng, đạo hữu {ten} đại thắng, khí thế ngút trời!\nKết thúc! Đạo hữu {ten} thắng gọn, đối thủ còn chưa kịp hiểu chuyện gì xảy ra!\nNăm quân thẳng hàng, đạo hữu {ten} thắng! Đạo hữu {thua} xin giữ bình tĩnh, uống ngụm trà là qua chuyện!\nXong phim rồi! Đạo hữu {ten} thắng, đạo hữu {thua} thua nhưng vẫn rất có tinh thần cố gắng!\nĐạo hữu {ten} thắng! Trận này là một màn trình diễn, mà đạo hữu {thua} là khán giả ngồi hàng đầu!' },
  { key: 'winForfeit', group: 'Kết quả', role: 'ref', label: 'Thắng do đối thủ bỏ cuộc / hết giờ', vars: ['ten', 'thua', 'lydo'],
    text: 'Đạo hữu {thua} {lydo}. Đạo hữu {ten} đắc thắng, khí chất vượt trội hơn mọi người!\nĐạo hữu {thua} {lydo}. Đạo hữu {ten} thắng mà chưa kịp nóng người, đúng là trúng mánh!\nĐạo hữu {thua} {lydo}! Đạo hữu {ten} thắng nhẹ nhàng như đi dạo, chúc mừng nhé!' },
  { key: 'congrats', group: 'Kết quả', role: 'mc', label: 'Chúc mừng người thắng', vars: ['ten'],
    text: 'Cung hỉ đạo hữu {ten}! Quả là xuất sắc, khí chất lộ rõ, tu vi cao thâm khó lường!\nCung hỉ đạo hữu {ten}! Khí thế ngút trời, danh tiếng vang xa, thiên hạ khó ai sánh bằng!\nCung hỉ, cung hỉ! Đạo hữu {ten} xuất sắc như vậy, quả là thiên tài cái thế, không ai sánh bằng!\nĐạo hữu {ten} một chiêu định càn khôn, khí chất rạng ngời. Xin chư vị đạo hữu cùng cung hỉ!\nCung hỉ đạo hữu {ten}! Cao thủ đây rồi, xin nhận của tại hạ một cái bái!\nĐạo hữu {ten} khí chất thế này, chắc ăn cơm bằng quân cờ! Cung hỉ, cung hỉ!\nChúc mừng đạo hữu {ten}! Đối thủ còn đang ngồi tự hỏi mình sai ở đâu, còn đạo hữu đã bay lên tiên!\nQuá xuất sắc! Đạo hữu {ten} đi nước nào là đối thủ toát mồ hôi nước đó, cung hỉ!\nCung hỉ đạo hữu {ten}! Nhìn đạo hữu đánh cờ mà tại hạ tưởng lạc vào giải đấu thế giới!' },
  { key: 'streak', group: 'Kết quả', role: 'mc', label: 'Thắng liên tiếp', vars: ['ten', 'so'],
    text: 'Đạo hữu {ten} đã liên tiếp thắng {so} trận, xuất sắc vô song, đạo hạnh thâm hậu, không ai theo kịp!\nĐạo hữu {ten} thắng {so} trận liên tiếp rồi! Các vị ơi, có ai theo kịp không, hay đi đâu hết rồi?\n{so} trận liền không thua, đạo hữu {ten} này chắc có bí kíp gia truyền! Ai biết xin chia sẻ cho tại hạ với!' },
  { key: 'rankUp', group: 'Kết quả', role: 'mc', label: 'Người thắng đột phá cảnh giới (rank)', vars: ['ten', 'canhgioi'],
    text: 'Thiên địa dị tượng! Đạo hữu {ten} đã đột phá, tiến nhập {canhgioi}, khung tu vi thêm rực rỡ!\nChúc mừng đạo hữu {ten} đột phá thành công, bước vào cảnh giới {canhgioi}, khí thế càng thêm ngút trời!\nĐạo hữu {ten} đột phá lên {canhgioi}! Mây lành tụ hội, hào quang rực rỡ, cung hỉ cung hỉ!\nChúc mừng đạo hữu {ten} lên {canhgioi}! Lên cấp nhanh như vậy chắc có uống đan dược trộm của sư phụ!\n{canhgioi}! Đạo hữu {ten} đã bước vào cảnh giới mới, từ nay ra đường phải có người xách dép!' },
  { key: 'rankDown', group: 'Kết quả', role: 'mc', label: 'Người thua độ kiếp thất bại (mất hết điểm)', vars: ['ten', 'canhgioi', 'diem'],
    text: 'Mây đen kéo tới! Đạo hữu {ten} độ kiếp thất bại, mất sạch {diem} điểm đạo hạnh! Xin chia buồn, hôm nay chưa hợp độ kiếp!\nĐộ kiếp thất bại! Đạo hữu {ten} độ kiếp chưa thành, mất {diem} điểm đạo hạnh, về lại {canhgioi}! Buồn hơn cả lỡ làm rơi cái bánh bao ăn dở!\nĐạo hữu {ten} thua một ván, độ kiếp thất bại, {diem} điểm đạo hạnh bay theo mây khói! Không sao, ngã ở đâu đứng dậy ở đó, tại hạ ủng hộ!\nÔi không! Kiếp nạn lần này hơi khó, đạo hữu {ten} độ kiếp chưa thành, mất hết điểm, nay phải tu lại từ {canhgioi}! Tâm đừng loạn nhé!\nChia buồn cùng đạo hữu {ten}, độ kiếp thất bại, mất {diem} điểm rồi! Mau về bế quan, hoặc ăn đan dược vào cho khỏe!' },
  { key: 'loseComfort', group: 'Kết quả', role: 'mc', label: 'Động viên người thua (chưa có điểm để mất)', vars: ['thua'],
    text: 'Đạo hữu {thua} đừng buồn, thua keo này ta bày keo khác, tiên nhân nào chẳng có lúc vấp ngã!\nĐạo hữu {thua} thua rồi nhưng phong độ vẫn đẹp, đúng là thua mà không mất khí thế!\nĐạo hữu {thua} cứ yên tâm, quân cờ thua chứ lòng người không thua, lần sau gỡ lại!\nThua một ván thôi mà, đạo hữu {thua} cứ uống chén trà cho tĩnh tâm, tu luyện lại là xong!' },
  { key: 'stepDown', group: 'Kết quả', role: 'mc', label: 'Đủ chuỗi thắng, nhường chỗ', vars: ['ten'],
    text: 'Đã đủ số trận liên thắng, xin đạo hữu nhường đài thi đấu cho người khác.\nĐủ chuỗi thắng rồi, đạo hữu xuống đài nghỉ chút đi, để người khác còn có cơ hội thể hiện!\nThắng nhiều quá rồi, xin nhường đài cho người khác thử sức nhé!' },
  { key: 'draw', group: 'Kết quả', role: 'ref', label: 'Hòa', vars: [],
    text: 'Bàn cờ đã kín quân. Hai bên bất phân thắng bại, hòa cục!\nHòa! Hai bên đánh hoài không phân thắng bại, chắc phải rủ nhau đi ăn mì tôm!\nBàn cờ kín quân mà không ai thắng, đúng là kỳ phùng địch thủ, hay hai bên cùng vụng!' },
  { key: 'hostReset', group: 'Khác', role: 'mc', label: 'Chủ phòng làm mới trận', vars: [],
    text: 'Chủ phòng đã khai mở lại trận pháp.\nChủ phòng vừa làm mới trận pháp, coi như chưa có gì xảy ra, ai thua cũng được tha!' },
  { key: 'remindFollow', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc bấm follow', vars: ['diem'],
    text: 'Nếu đạo hữu thấy hữu duyên, xin hãy follow để khỏi lỡ các buổi tiên hội sau nhé!\nNếu thấy vui, đạo hữu có thể follow để gặp lại ở các buổi sau nhé!\nĐạo hữu nào muốn xem tiếp các buổi sau thì có thể follow nhé!\nĐạo hữu nào thấy vui thì follow nhé, không bấm cũng không sao, cứ ngồi xem thoải mái!' },
  { key: 'remindShare', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc chia sẻ', vars: ['diem'],
    text: 'Nếu thấy vui, đạo hữu hãy chia sẻ buổi LIVE này cho bằng hữu nhé!\nNếu thấy vui, đạo hữu có thể rủ thêm bạn bè vào xem nhé!\nBạn bè nào thích cờ thì đạo hữu có thể chia sẻ buổi live cho họ nhé!\nCó thể chia sẻ buổi live cho bạn bè nếu thấy vui, không bắt buộc đâu nhé!' },
  { key: 'extraTime', group: 'Trong ván', role: 'ref', label: 'Người chơi xin thêm giờ', vars: ['ten', 'giay'],
    text: 'Đạo hữu {ten} xin thêm {giay} giây. Mời tiếp tục suy diễn!\nĐạo hữu {ten} xin thêm {giay} giây! Xin cứ nghĩ cho kỹ, nhưng đừng nghĩ đến mai nhé!\nCho đạo hữu {ten} thêm {giay} giây suy diễn! Xin hãy dùng cho đúng chỗ, đừng dùng để lướt điện thoại!' },
  { key: 'confirmAsk', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 2 người thả tim xác nhận', vars: ['ten1', 'ten2', 'giay'],
    text: 'Mời đạo hữu {ten1} và đạo hữu {ten2} thả tim để xác nhận lên đài. Chỉ còn {giay} giây!\nMời {ten1} và {ten2} thả tim xác nhận lên đài! Còn {giay} giây!\nHai vị {ten1}, {ten2}, mời thả tim để xác nhận! Còn {giay} giây!' },
  { key: 'confirmAskOne', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 1 người thả tim xác nhận', vars: ['ten', 'giay'],
    text: 'Mời đạo hữu {ten} thả tim để xác nhận lên đài. Chỉ còn {giay} giây!\nMời đạo hữu {ten} thả tim xác nhận! Chỉ một cái chạm thôi, còn {giay} giây!' },
  { key: 'confirmOk', group: 'Xác nhận thả tim', role: 'mc', label: 'Một người đã xác nhận', vars: ['ten'],
    text: 'Đạo hữu {ten} đã sẵn sàng!\nĐạo hữu {ten} đã thả tim, sẵn sàng thi đấu rồi, quả là người có trách nhiệm!\nTim đã tới! Đạo hữu {ten} xác nhận xong, giờ chỉ còn chờ đối thủ nữa thôi!' },
  { key: 'confirmWarn', group: 'Xác nhận thả tim', role: 'mc', label: 'Sắp hết giờ xác nhận', vars: ['ten', 'giay'],
    text: 'Đạo hữu {ten} ơi, mau thả tim để giữ suất, còn {giay} giây!\nĐạo hữu {ten} ơi, còn {giay} giây! Mời thả tim để xác nhận!\nĐạo hữu {ten} ơi, còn {giay} giây để xác nhận nhé!' },
  { key: 'confirmFail', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, mời người khác thay', vars: ['ten', 'ten2'],
    text: 'Đạo hữu {ten} chưa thả tim nên mất suất. Mời đạo hữu {ten2} thế chỗ, xin thả tim để xác nhận!\nĐạo hữu {ten} chưa kịp xác nhận nên mất suất. Mời đạo hữu {ten2} thế chỗ, xin thả tim để xác nhận!\nĐạo hữu {ten} chưa xác nhận kịp nên mất suất. Mời {ten2} lên thay!' },
  { key: 'confirmFailNone', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, không còn ai thay', vars: ['ten'],
    text: 'Đạo hữu {ten} chưa thả tim nên mất suất. Chúng ta sẽ chọn lại người lên đài nhé!\nĐạo hữu {ten} không thả tim nên mất suất, mà cũng chẳng có ai thay! Thôi, chọn lại từ đầu nào!' },
  { key: 'giftThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn tặng quà', vars: ['ten', 'qua', 'so'],
    text: 'Đa tạ đạo hữu {ten} đã tặng {qua}!\nĐa tạ đạo hữu {ten} đã ban tặng {qua}, thật là hào phóng!\nÔ, đạo hữu {ten} vừa tặng {qua}! Tại hạ vô cùng cảm kích!\nOa, đạo hữu {ten} tặng {qua}! Tại hạ cảm động đến mức quên mất mình đang cầm micro!\nCảm ơn đạo hữu {ten} đã tặng {qua}! Hào phóng thế này, kiếp sau tại hạ xin làm trâu ngựa!\nĐạo hữu {ten} vừa tặng {qua}! Quà đến tay, tâm hồn tại hạ như được tắm nước linh tuyền!\nTạ ơn đạo hữu {ten} vì {qua}! Chắc đạo hữu là con nhà đại gia tiên giới rồi!' },
  { key: 'giftBig', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn quà LỚN', vars: ['ten', 'qua', 'so'],
    text: 'Chấn động! Đa tạ đạo hữu {ten} đã tặng {qua}. Quả là đại thiện nhân!\nTrời ơi, {qua} từ đạo hữu {ten}! Tại hạ xin đa tạ, ân đức này xin ghi tạc!\nTrời đất ơi, {qua} từ đạo hữu {ten}! Tại hạ xin quỳ một cái cho đỡ ngại, thiên địa cũng phải nghiêng mình!\nĐại gia {ten} xuất hiện tặng {qua}! Mọi người nhớ mặt vị này nhé, tương lai làm tông chủ đó!\nChấn động bát phương, {qua} của đạo hữu {ten}! Tại hạ xin ghi tên vào gia phả, sáng thắp hương chiều đốt vàng mã!' },
  { key: 'followThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn follow', vars: ['ten'],
    text: 'Đa tạ đạo hữu {ten} đã follow, kết duyên cùng chúng ta!\nCảm ơn đạo hữu {ten} đã follow! Từ nay mình là người một nhà, chung một tông môn, thua thì cùng nhau khóc!\nĐạo hữu {ten} vừa follow! Chào mừng gia nhập hội, phí gia nhập là một nụ cười!' },
  { key: 'shareThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn chia sẻ LIVE', vars: ['ten'],
    text: 'Đa tạ đạo hữu {ten} đã chia sẻ buổi LIVE!\nĐạo hữu {ten} chia sẻ live rồi! Đúng là bằng hữu chân chính, tại hạ cảm động rơi lệ, giả vờ thôi!\nCảm ơn đạo hữu {ten} đã share! Hy vọng bằng hữu của đạo hữu đến thật đông, cùng nhau thi thố!' },
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
          const kept = v.text.split('\n').filter((l) => !VIOLENT.test(l) && !checkLine(l)); // bỏ cả câu vi phạm quy định LIVE đã lưu từ trước
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
