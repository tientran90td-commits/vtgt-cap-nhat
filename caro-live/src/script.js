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
  diem: 'số điểm thưởng',
  giay: 'số giây',
  qua: 'tên món quà',
  so: 'số lượng / số ván',
  lydo: 'lý do xử thua',
  canhgioi: 'tên cảnh giới (rank)',
};

// role: 'mc' = điều phối viên, 'ref' = trọng tài
const DEFAULTS = [
  { key: 'welcome', group: 'Mở đầu', role: 'mc', label: 'Chào mừng (vòng đầu tiên)', vars: ['giay'],
    text: 'Hoan nghênh chư vị đạo hữu giá lâm Caro Tiên Giới! Chư vị hãy bình luận, thả tim hoặc tặng lễ vật để giành suất lên đài luận võ. Chỉ còn {giay} giây!\nChào mừng chư vị đến Caro Tiên Giới! Nơi đây không bán đan dược, chỉ bán sự căng thẳng! Bình luận, thả tim để lên đài, chỉ còn {giay} giây!\nĐệ tử mới đến thì cứ thả tim trước, hỏi han sau! Tại hạ hứa không cắn ai, chỉ cắn quân cờ. Còn {giay} giây tranh suất lên đài!\nCaro Tiên Giới khai mở! Ai thắng thì thành tiên, ai thua thì về tu luyện lại. Mau tương tác, chỉ còn {giay} giây!' },
  { key: 'lobbyStart', group: 'Mở đầu', role: 'mc', label: 'Bắt đầu vòng mới', vars: ['giay'],
    text: 'Một vòng tranh đài mới đã mở! Chư vị đạo hữu hãy bình luận, thả tim hoặc tặng lễ vật để giành suất lên đài. Chỉ còn {giay} giây!\nVòng mới tới rồi! Ai chưa tu luyện thì tranh thủ gõ vài câu bình luận, còn {giay} giây thôi, đừng để tiên duyên trôi mất!\nLôi đài mở cửa, đạo hữu nào dám lên? Không dám thì thả tim cho có khí thế cũng được! Còn {giay} giây!\nMột vòng tranh đài nữa! Tay nhanh thì được lên đài, tay chậm thì ngồi xem hạt dưa nhé! Còn {giay} giây!' },
  { key: 'howTo', group: 'Mở đầu', role: 'mc', label: 'Giải thích cách chơi (lúc chờ)', vars: [],
    text: 'Quy củ rất đơn giản: đến lượt mình, đạo hữu hãy bình luận tọa độ, ví dụ j chín, để bố trận. Ai kết được năm quân liền một đường là thắng. Muốn lên đài, chư vị hãy bình luận, thả tim và tặng lễ vật!\nPháp môn rất dễ: gõ cột và hàng, như ca sáu, để xuất chiêu. Năm quân nối liền là đại thắng, kể cả bị chặn hai đầu. Tích cực bình luận, thả tim, tặng lễ vật để được chọn lên đài nhé, chư vị đạo hữu!\nCách chơi dễ như ăn cháo: gõ cột và hàng, ví dụ j chín, là xong. Còn ai gõ nhầm thì thiên đạo cũng không cứu nổi đâu!\nNhớ nhé: năm quân thẳng hàng là thắng, bốn quân thì chưa, ba quân thì về nhà ngủ đi! Muốn lên đài thì bình luận, thả tim, tặng quà!' },
  { key: 'greet', group: 'Mở đầu', role: 'mc', label: 'Chào người mới vào', vars: ['ten'],
    text: 'Hoan nghênh đạo hữu {ten} ghé thăm! Hãy bình luận hoặc thả tim để giành suất lên đài nhé.\nBái kiến đạo hữu {ten}! Chúc đạo hữu tiêu dao thưởng lãm, nhớ bình luận để được chọn lên đài nha.\nÔi, đạo hữu {ten} ghé thăm! Ngồi xuống uống chén trà, rồi bình luận để lên đài luôn nhé!\nBái kiến đạo hữu {ten}! Nghe nói đạo hữu cờ rất cao thâm, hôm nay cho tại hạ chiêm ngưỡng xem sao!\nChào đạo hữu {ten}! Cửa tiên giới mở rộng, nhưng bình luận mới là chìa khóa. Mau gõ vài chữ đi nào!' },
  { key: 'lobbyWarn', group: 'Mở đầu', role: 'mc', label: 'Sắp hết giờ đua tương tác', vars: ['ten', 'ten1', 'ten2'],
    text: 'Còn mười giây nữa! Đạo hữu {ten} đang dẫn đầu bảng tương tác.\nCòn mười giây! Đạo hữu {ten} đang dẫn đầu, các vị khác còn ngồi đó làm gì, thả tim đi chứ!\nMười giây cuối! Đạo hữu {ten} đang dẫn đầu bảng, ai muốn cướp ngôi thì ngay bây giờ hoặc không bao giờ!\nSắp hết giờ rồi, tim đâu, tim đâu! Đạo hữu {ten} đang chạy nhanh nhất, các vị tăng tốc giùm tại hạ!' },
  { key: 'lobbyEmpty', group: 'Mở đầu', role: 'mc', label: 'Chưa có ai lên bàn', vars: [],
    text: 'Trên đài chưa có đạo hữu nào. Mời chư vị bình luận hoặc thả tim để lên đài luận võ!\nTrên đài vắng như chùa bà đanh! Chư vị đạo hữu đâu hết rồi, bình luận một câu cho tại hạ đỡ buồn!\nKhông có ai lên đài hết, tại hạ sắp ngủ gật rồi đây! Thả tim hoặc bình luận đi mà!' },
  { key: 'pickedPair', group: 'Chọn người chơi', role: 'mc', label: 'Công bố 2 người chơi', vars: ['ten1', 'ten2'],
    text: 'Hai vị đạo hữu được chọn lên đài là {ten1} và {ten2}. Xin chúc mừng!\nĐài chiến đã có chủ: {ten1} đại chiến {ten2}! Một bên là mãnh hổ, một bên cũng mãnh hổ, xem ai ăn ai!\nHai vị đạo hữu {ten1} và {ten2} lên đài! Xin chư vị chuẩn bị hạt dưa nước ngọt, trò hay sắp bắt đầu!\nMời {ten1} và {ten2} bước lên lôi đài! Nhớ đừng run tay, quân cờ không cắn người đâu!' },
  { key: 'pickedChamp', group: 'Chọn người chơi', role: 'mc', label: 'Người thắng ở lại, có người thách đấu', vars: ['ten1', 'ten2'],
    text: 'Đạo hữu {ten1} tiếp tục trấn giữ lôi đài, và sẽ tỷ thí cùng đạo hữu {ten2}.\nĐạo hữu {ten1} vẫn ngồi vững trên đài, chưa chịu đi! Hôm nay đạo hữu {ten2} liệu có đá được ra không?\nLại là {ten1} trấn đài! Đạo hữu {ten2} xông lên, hy vọng không bị đánh cho về quê!' },
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
  { key: 'warn10', group: 'Trong ván', role: 'ref', label: 'Cảnh báo còn 10 giây', vars: ['ten'],
    text: 'Đạo hữu {ten}, chỉ còn mười giây, mau suy diễn!\nĐạo hữu {ten} ơi, mười giây thôi đó! Nghĩ nhanh lên, kẻo đồng hồ làm thịt bây giờ!\nCòn mười giây! Đạo hữu {ten} nghĩ kỹ chưa, hay đang ngủ gật?\nMười giây nữa là hết giờ rồi đạo hữu {ten}! Tim tại hạ còn đập nhanh hơn đạo hữu nghĩ đó!' },
  { key: 'timeoutAuto', group: 'Trong ván', role: 'ref', label: 'Hết giờ, đánh thay', vars: ['ten', 'oco'],
    text: 'Đạo hữu {ten} đã hết thời gian. Thiên đạo đánh thay vào ô {oco}.\nĐạo hữu {ten} nghĩ lâu quá, thiên đạo đành đánh thay vào {oco}! Dở thì đừng trách thiên đạo nhé!\nHết giờ rồi! Thiên đạo thay đạo hữu {ten} đánh {oco}. Hy vọng thiên đạo cờ cao hơn đạo hữu!' },
  { key: 'winGame', group: 'Kết quả', role: 'ref', label: 'Có người thắng', vars: ['ten', 'thua', 'so'],
    text: 'Trận tỷ thí kết thúc! Đạo hữu {ten} kết thành năm quân liền một đường, đại thắng!\nKết thúc rồi! Đạo hữu {ten} một chiêu phá trận, năm quân liền một đường, bá đạo vô song!\nNăm quân đã thành hàng, đạo hữu {ten} đại thắng, khí thế ngút trời!\nKết thúc! Đạo hữu {ten} thắng gọn, đối thủ còn chưa kịp hiểu chuyện gì xảy ra!\nNăm quân thẳng hàng, đạo hữu {ten} thắng! Đạo hữu {thua} xin giữ bình tĩnh, uống ngụm trà là qua chuyện!\nXong phim rồi! Đạo hữu {ten} thắng, đạo hữu {thua} thua nhưng vẫn rất có tinh thần cố gắng!\nĐạo hữu {ten} thắng! Trận này là một màn trình diễn, mà đạo hữu {thua} là khán giả ngồi hàng đầu!' },
  { key: 'winForfeit', group: 'Kết quả', role: 'ref', label: 'Thắng do đối thủ bỏ cuộc / hết giờ', vars: ['ten', 'thua', 'lydo'],
    text: 'Đạo hữu {thua} {lydo}. Đạo hữu {ten} đắc thắng, bá khí lấn át quần hùng!\nĐạo hữu {thua} {lydo}. Đạo hữu {ten} thắng mà chưa kịp nóng người, đúng là trúng mánh!\nĐạo hữu {thua} {lydo}! Đạo hữu {ten} thắng nhẹ nhàng như đi dạo, chúc mừng nhé!' },
  { key: 'congrats', group: 'Kết quả', role: 'mc', label: 'Chúc mừng người thắng', vars: ['ten'],
    text: 'Cung hỉ đạo hữu {ten}! Quả là bá đạo, bá khí lộ rõ, tu vi cao thâm khó lường!\nCung hỉ đạo hữu {ten}! Bá khí ngút trời, uy chấn bát phương, thiên hạ khó có địch thủ!\nCung hỉ, cung hỉ! Đạo hữu {ten} bá đạo như vậy, quả là thiên tài cái thế, không ai sánh bằng!\nĐạo hữu {ten} một chiêu định càn khôn, bá khí lẫm liệt. Xin chư vị đạo hữu cùng cung hỉ!\nCung hỉ đạo hữu {ten}! Cao thủ đây rồi, xin nhận của tại hạ một cái bái!\nĐạo hữu {ten} bá khí thế này, chắc ăn cơm bằng quân cờ! Cung hỉ, cung hỉ!\nChúc mừng đạo hữu {ten}! Đối thủ còn đang ngồi tự hỏi mình sai ở đâu, còn đạo hữu đã bay lên tiên!\nQuá bá đạo! Đạo hữu {ten} đi nước nào là đối thủ toát mồ hôi nước đó, cung hỉ!\nCung hỉ đạo hữu {ten}! Nhìn đạo hữu đánh cờ mà tại hạ tưởng lạc vào phim kiếm hiệp!' },
  { key: 'streak', group: 'Kết quả', role: 'mc', label: 'Thắng liên tiếp', vars: ['ten', 'so'],
    text: 'Đạo hữu {ten} đã liên tiếp thắng {so} trận, bá đạo vô song, đạo hạnh thâm hậu, không ai cản nổi!\nĐạo hữu {ten} thắng {so} trận liên tiếp rồi! Đối thủ ơi, có ai ngăn được không, hay chạy trốn hết rồi?\n{so} trận liền không thua, đạo hữu {ten} này chắc có bí kíp gia truyền! Ai biết xin chia sẻ cho tại hạ với!' },
  { key: 'rankUp', group: 'Kết quả', role: 'mc', label: 'Người thắng đột phá cảnh giới (rank)', vars: ['ten', 'canhgioi'],
    text: 'Thiên địa dị tượng! Đạo hữu {ten} đã đột phá, tiến nhập {canhgioi}, khung tu vi thêm rực rỡ!\nChúc mừng đạo hữu {ten} đột phá thành công, bước vào cảnh giới {canhgioi}, bá khí càng thêm ngút trời!\nĐạo hữu {ten} đột phá lên {canhgioi}! Sấm sét đùng đùng, mây mù bay tứ tán, cung hỉ cung hỉ!\nChúc mừng đạo hữu {ten} lên {canhgioi}! Lên cấp nhanh như vậy chắc có uống đan dược trộm của sư phụ!\n{canhgioi}! Đạo hữu {ten} đã bước vào cảnh giới mới, từ nay ra đường phải có người xách dép!' },
  { key: 'rankDown', group: 'Kết quả', role: 'mc', label: 'Người thua bị tụt cảnh giới (rank)', vars: ['ten', 'canhgioi'],
    text: 'Ôi không! Đạo hữu {ten} tẩu hỏa nhập ma, rớt xuống {canhgioi} rồi! Xin chia buồn, hôm nay không hợp luyện công!\nĐạo hữu {ten} thua một ván, tu vi rơi tự do xuống {canhgioi}! Đau lòng hơn cả bị sư phụ đuổi khỏi tông môn!\nHạ rank rồi! Đạo hữu {ten} nay lùi về {canhgioi}, không sao, ngã ở đâu đứng dậy ở đó, tại hạ ủng hộ!\nĐạo hữu {ten} bị đánh rớt xuống {canhgioi}! Mau về bế quan luyện thêm, hoặc ăn đan dược vào cho khỏe!\nChia buồn cùng đạo hữu {ten}, nay phải tu lại từ {canhgioi}! Tâm đừng loạn, mai lại là một ngày nắng đẹp!' },
  { key: 'loseComfort', group: 'Kết quả', role: 'mc', label: 'Động viên người thua (không bị hạ rank)', vars: ['thua'],
    text: 'Đạo hữu {thua} đừng buồn, thua keo này ta bày keo khác, tiên nhân nào chẳng có lúc vấp ngã!\nĐạo hữu {thua} thua rồi nhưng phong độ vẫn đẹp, đúng là thua mà không mất khí thế!\nĐạo hữu {thua} cứ yên tâm, quân cờ thua chứ lòng người không thua, lần sau báo thù!\nThua một ván thôi mà, đạo hữu {thua} cứ uống chén trà cho tĩnh tâm, tu luyện lại là xong!' },
  { key: 'stepDown', group: 'Kết quả', role: 'mc', label: 'Đủ chuỗi thắng, nhường chỗ', vars: ['ten'],
    text: 'Đã đủ số trận liên thắng, xin đạo hữu nhường lôi đài cho người khác.\nĐủ chuỗi thắng rồi, đạo hữu xuống đài nghỉ chút đi, để người khác còn có cơ hội bị đánh!\nThắng nhiều quá rồi, xin nhường đài cho người khác ăn hành, à nhầm, ăn cơ hội!' },
  { key: 'draw', group: 'Kết quả', role: 'ref', label: 'Hòa', vars: [],
    text: 'Bàn cờ đã kín quân. Hai bên bất phân thắng bại, hòa cục!\nHòa! Hai bên đánh hoài không phân thắng bại, chắc phải rủ nhau đi ăn mì tôm!\nBàn cờ kín quân mà không ai thắng, đúng là kỳ phùng địch thủ, hay hai bên cùng vụng!' },
  { key: 'hostReset', group: 'Khác', role: 'mc', label: 'Chủ phòng làm mới trận', vars: [],
    text: 'Chủ phòng đã khai mở lại trận pháp.\nChủ phòng vừa làm mới trận pháp, coi như chưa có gì xảy ra, ai thua cũng được tha!' },
  { key: 'remindFollow', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc bấm follow', vars: ['diem'],
    text: 'Nếu đạo hữu thấy hữu duyên, xin hãy follow để khỏi lỡ các buổi tiên hội sau! Follow ngay được cộng {diem} điểm tương tác.\nVị đạo hữu nào chưa follow, xin bấm giúp tại hạ một cái, sẽ được cộng {diem} điểm để giành suất lên đài!\nĐạo hữu nào lỡ bước ngang qua mà chưa follow thì bấm giúp tại hạ một cái! Bấm xong được cộng {diem} điểm, không bấm cũng không sao, tại hạ chỉ hơi buồn thôi!\nFollow một cái là có thêm bạn tu tiên, được cộng {diem} điểm, lại còn đỡ lạc đường lần sau, hời quá còn gì!' },
  { key: 'remindShare', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc chia sẻ', vars: ['diem'],
    text: 'Hãy chia sẻ buổi LIVE này cho bằng hữu để cùng đến luận võ! Chia sẻ được cộng {diem} điểm tương tác.\nMời thêm đồng đạo vào xem và tỷ thí, chia sẻ live là được cộng {diem} điểm đó!\nChia sẻ live cho bằng hữu đi nào! Rủ thêm người vào cho đông vui, được cộng {diem} điểm, lại có người cùng thua với mình!\nShare live đi đạo hữu, được {diem} điểm! Đừng giữ tiên cảnh này một mình, ích kỷ quá thiên đạo trách đó!' },
  { key: 'extraTime', group: 'Trong ván', role: 'ref', label: 'Người chơi xin thêm giờ', vars: ['ten', 'giay'],
    text: 'Đạo hữu {ten} xin thêm {giay} giây. Mời tiếp tục suy diễn!\nĐạo hữu {ten} xin thêm {giay} giây! Xin cứ nghĩ cho kỹ, nhưng đừng nghĩ đến mai nhé!\nCho đạo hữu {ten} thêm {giay} giây suy diễn! Xin hãy dùng cho đúng chỗ, đừng dùng để lướt điện thoại!' },
  { key: 'confirmAsk', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 2 người thả tim xác nhận', vars: ['ten1', 'ten2', 'giay'],
    text: 'Mời đạo hữu {ten1} và đạo hữu {ten2} thả tim để xác nhận lên đài. Chỉ còn {giay} giây!\nMời {ten1} và {ten2} thả tim xác nhận lên đài! Còn {giay} giây, không thả là mất suất đó, tim đâu tim đâu!\nHai vị {ten1}, {ten2}, thả tim một cái cho tại hạ yên tâm nào! Còn {giay} giây thôi!' },
  { key: 'confirmAskOne', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 1 người thả tim xác nhận', vars: ['ten', 'giay'],
    text: 'Mời đạo hữu {ten} thả tim để xác nhận lên đài. Chỉ còn {giay} giây!\nMời đạo hữu {ten} thả tim xác nhận! Chỉ một cái chạm thôi mà, đừng bắt tại hạ chờ lâu, còn {giay} giây!' },
  { key: 'confirmOk', group: 'Xác nhận thả tim', role: 'mc', label: 'Một người đã xác nhận', vars: ['ten'],
    text: 'Đạo hữu {ten} đã sẵn sàng!\nĐạo hữu {ten} đã thả tim, sẵn sàng chiến đấu rồi, quả là người có trách nhiệm!\nTim đã tới! Đạo hữu {ten} xác nhận xong, giờ chỉ còn chờ đối thủ nữa thôi!' },
  { key: 'confirmWarn', group: 'Xác nhận thả tim', role: 'mc', label: 'Sắp hết giờ xác nhận', vars: ['ten', 'giay'],
    text: 'Đạo hữu {ten} ơi, mau thả tim để giữ suất, còn {giay} giây!\nĐạo hữu {ten} ơi, còn {giay} giây! Thả tim nhanh kẻo suất lên đài bay đi mất đó!\nTim đâu rồi đạo hữu {ten}? Còn {giay} giây thôi, đừng để tại hạ phải gọi hồn!' },
  { key: 'confirmFail', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, mời người khác thay', vars: ['ten', 'ten2'],
    text: 'Đạo hữu {ten} chưa thả tim nên mất suất. Mời đạo hữu {ten2} thế chỗ, xin thả tim để xác nhận!\nĐạo hữu {ten} không thả tim, mất suất rồi, tiếc quá! Mời đạo hữu {ten2} thế chỗ, nhớ thả tim đó!\nĐạo hữu {ten} ngủ quên rồi sao? Không thả tim nên mất suất. Mời {ten2} lên thay!' },
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
        if (typeof v.text === 'string') it.custom = v.text;
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
