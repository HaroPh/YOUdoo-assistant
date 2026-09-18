# Bang chung dap an cho HARD_EXPANSION_CASES

Sinh tu `evals/hard_expansion_sample.json` (seed 20260918). Cau hoi do agent
viet MU (khong thay spec, khong thay ket qua do, khong biet dang so sanh
reranker nao) - chi doc dung 3 file duoc phep: `hard_expansion_sample.json`,
`hard_gate.py`, va brief cua task nay. Moi ca mot muc:

## 1. discount_policy.docx › Chính sách chiết khấu theo cấp khách hàng › Mục 5 — Rà soát và điều chỉnh
- **Câu hỏi:** Nếu doanh số của khách hàng không đạt mức duy trì hạng trong hai quý liên tiếp thì chuyện gì sẽ xảy ra với hạng của họ?
- **Trích dẫn (nguyên văn trong chunk):** "Khách hàng không đạt doanh số duy trì cấp trong 2 quý liên tiếp bị hạ xuống cấp thấp hơn."
- **overlap:** 0,33 — **viết lại:** 0 lần

## 2. payment_policy.docx › Chính sách thanh toán và công nợ khách hàng › Điều 5 — Đối chiếu công nợ
- **Câu hỏi:** Nếu thấy khoản phải trả bị ghi sai, khách hàng có mấy ngày làm việc để lên tiếng trước khi số liệu được xem là đã được chấp nhận?
- **Trích dẫn (nguyên văn trong chunk):** "Khách hàng có 5 ngày làm việc để phản hồi nếu có sai lệch; quá thời hạn, số liệu công nợ được xem là đã xác nhận."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 3. sla.docx › Thỏa thuận mức dịch vụ nhà cung cấp › Điều 6 — Thanh toán
- **Câu hỏi:** Nhà cung cấp được giảm bao nhiêu phần trăm nếu trả tiền cho công ty trong vòng 10 ngày kể từ khi nhận hóa đơn?
- **Trích dẫn (nguyên văn trong chunk):** "Chiết khấu 2% áp dụng nếu thanh toán trong vòng 10 ngày."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 4. sop.docx › Quy trình nhập kho › Bước 4 — Cập nhật hệ thống
- **Câu hỏi:** Sau khi kiểm tra hàng nhập kho xong, nhân viên phải nhập số liệu tồn kho vào đâu?
- **Trích dẫn (nguyên văn trong chunk):** "Sau khi kiểm tra xong, nhân viên cập nhật số lượng tồn kho vào Odoo."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 5. sales_process.docx › Quy trình bán hàng › Mục 4 — Giao hàng và đối chiếu
- **Câu hỏi:** Khi phát hiện hàng thực nhận không khớp với đơn đặt, nhân viên bán hàng phải báo lại trong thời gian bao lâu?
- **Trích dẫn (nguyên văn trong chunk):** "Sai lệch giữa hàng giao và đơn hàng phải được ghi nhận và báo lại cho nhân viên bán hàng trong ngày."
- **overlap:** 0,17 — **viết lại:** 0 lần

## 6. warehouse_outbound.docx › Quy trình xuất kho › Mục 2 — Kiểm tra tồn kho và soạn hàng
- **Câu hỏi:** Với những mặt hàng có hạn sử dụng, kho phải ưu tiên lấy lô nào ra trước?
- **Trích dẫn (nguyên văn trong chunk):** "Ưu tiên xuất hàng theo nguyên tắc nhập trước xuất trước (FIFO) đối với hàng có hạn sử dụng."
- **overlap:** 0,25 — **viết lại:** 0 lần

## 7. boluat-danssu.pdf › Chương III › CÁ NHÂN › Mục 4. GIÁM HỘ › Điều 50. Điều kiện của pháp nhân làm người giám hộ
- **Câu hỏi:** Một tổ chức (không phải cá nhân) muốn đứng ra chăm sóc và bảo vệ quyền lợi thay cho người không đủ năng lực hành vi dân sự thì phải đáp ứng những gì?
- **Trích dẫn (nguyên văn trong chunk):** "Pháp nhân có đủ các điều kiện sau đây có thể làm người giám hộ: 1. Có năng lực pháp luật dân sự phù hợp với việc giám hộ. 2. Có điều kiện cần thiết để thực hiện quyền, nghĩa vụ của người giám hộ."
- **overlap:** 0,20 — **viết lại:** 0 lần

## 8. boluat-danssu.pdf › Chương IX › ĐẠI DIỆN › Điều 134. Đại diện
- **Câu hỏi:** Có phải khi nào cũng được nhờ người khác đứng ra thay mặt mình xác lập một giao dịch dân sự không?
- **Trích dẫn (nguyên văn trong chunk):** "Cá nhân không được để người khác đại diện cho mình nếu pháp luật quy định họ phải tự mình xác lập, thực hiện giao dịch đó."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 9. boluat-danssu.pdf › Chương X › QUY ĐỊNH CHUNG › Mục 1. NGUYÊN TẮC XÁC LẬP, THỰC HIỆN QUYỀN SỞ HỮU, QUYỀN KHÁC ĐỐI VỚI TÀI SẢN › Điều 158. Quyền sở hữu
- **Câu hỏi:** Được làm chủ một tài sản thì có những quyền cụ thể nào đối với nó?
- **Trích dẫn (nguyên văn trong chunk):** "Quyền sở hữu bao gồm quyền chiếm hữu, quyền sử dụng và quyền định đoạt tài sản của chủ sở hữu theo quy định của luật."
- **overlap:** 0,20 — **viết lại:** 0 lần

## 10. boluat-danssu.pdf › Chương XIII › QUYỀN SỞ HỮU › Mục 1. NỘI DUNG QUYỀN SỞ HỮU › Điều 188. Quyền chiếm hữu của người được giao tài sản thông qua giao dịch dân sự
- **Câu hỏi:** Nếu chỉ được giao đồ dùng để dùng tạm mà không được chuyển quyền sở hữu, người nhận có được cho người khác mượn lại đồ đó không?
- **Trích dẫn (nguyên văn trong chunk):** "Người được giao tài sản có quyền sử dụng tài sản được giao, được chuyển quyền chiếm hữu, sử dụng tài sản đó cho người khác nếu được chủ sở hữu đồng ý."
- **overlap:** 0,31 — **viết lại:** 0 lần

## 11. boluat-danssu.pdf › Chương XIII › QUYỀN SỞ HỮU › Mục 3. XÁC LẬP, CHẤM DỨT QUYỀN SỞ HỮU › Điều 233. Xác lập quyền sở hữu đối với vật nuôi dưới nước
- **Câu hỏi:** Nếu phát hiện cá lạ bơi vào ao nhà mình, phải thông báo công khai bao lâu trước khi được xem là của mình luôn?
- **Trích dẫn (nguyên văn trong chunk):** "Sau 01 tháng, kể từ ngày thông báo công khai mà không có người đến nhận thì quyền sở hữu vật nuôi dưới nước đó thuộc về người có ruộng, ao, hồ."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 12. boluat-danssu.pdf › Chương XIV › QUY ĐỊNH CHUNG › Mục 3. BẢO ĐẢM THỰC HIỆN NGHĨA VỤ › Điều 307. Thanh toán số tiền có được từ việc xử lý tài sản cầm cố, thế chấp
- **Câu hỏi:** Khi ngân hàng phát mãi tài sản bảo đảm mà thu được nhiều tiền hơn khoản nợ, phần chênh lệch dư ra thuộc về ai?
- **Trích dẫn (nguyên văn trong chunk):** "Trường hợp số tiền có được từ việc xử lý tài sản cầm cố, thế chấp sau khi thanh toán chi phí bảo quản, thu giữ và xử lý tài sản cầm cố, thế chấp lớn hơn giá trị nghĩa vụ được bảo đảm thì số tiền chênh lệch phải được trả cho bên bảo đảm."
- **overlap:** 0,24 — **viết lại:** 0 lần

## 13. boluat-danssu.pdf › Chương XIV › QUY ĐỊNH CHUNG › Mục 4. TRÁCH NHIỆM DÂN SỰ › Điều 353. Chậm thực hiện nghĩa vụ
- **Câu hỏi:** Nếu một bên trễ hẹn không hoàn thành đúng hạn cam kết, họ có phải báo cho bên kia biết không?
- **Trích dẫn (nguyên văn trong chunk):** "Bên chậm thực hiện nghĩa vụ phải thông báo ngay cho bên có quyền về việc không thực hiện nghĩa vụ đúng thời hạn."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 14. boluat-danssu.pdf › Chương XIV › QUY ĐỊNH CHUNG › Mục 7. HỢP ĐỒNG › Điều 399. Địa điểm giao kết hợp đồng
- **Câu hỏi:** Nếu hai bên ký hợp đồng mà không thỏa thuận trước nơi ký, thì hợp đồng được xem là ký ở đâu?
- **Trích dẫn (nguyên văn trong chunk):** "Địa điểm giao kết hợp đồng do các bên thỏa thuận; nếu không có thỏa thuận thì địa điểm giao kết hợp đồng là nơi cư trú của cá nhân hoặc trụ sở của pháp nhân đã đưa ra đề nghị giao kết hợp đồng."
- **overlap:** 0,25 — **viết lại:** 0 lần

## 15. boluat-danssu.pdf › Chương XIV › QUYỀN KHÁC ĐỐI VỚI TÀI SẢN › Mục 2. QUYỀN HƯỞNG DỤNG › Điều 261. Quyền của người hưởng dụng
- **Câu hỏi:** Ai đó không phải chủ nhưng đang được lâu dài khai thác, thu lợi từ một tài sản, có được cho bên khác thuê lại phần khai thác ấy không?
- **Trích dẫn (nguyên văn trong chunk):** "Cho thuê quyền hưởng dụng đối với tài sản."
- **overlap:** 0,00 — **viết lại:** 1 lần

## 16. boluat-danssu.pdf › Chương XVI › MỘT SỐ HỢP ĐỒNG THÔNG DỤNG › Mục 10. HỢP ĐỒNG VẬN CHUYỂN › Điều 524. Nghĩa vụ của bên vận chuyển
- **Câu hỏi:** Công ty xe khách có bắt buộc phải mua bảo hiểm trách nhiệm dân sự cho hành khách không?
- **Trích dẫn (nguyên văn trong chunk):** "Mua bảo hiểm trách nhiệm dân sự đối với hành khách theo quy định của pháp luật."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 17. boluat-danssu.pdf › Chương XVI › MỘT SỐ HỢP ĐỒNG THÔNG DỤNG › Mục 2. HỢP ĐỒNG TRAO ĐỔI TÀI SẢN › Điều 456. Thanh toán giá trị chênh lệch
- **Câu hỏi:** Khi hai bên đổi tài sản cho nhau mà giá trị hai món không bằng nhau, phần thiếu phải xử lý thế nào?
- **Trích dẫn (nguyên văn trong chunk):** "Trường hợp tài sản trao đổi chênh lệch về giá trị thì các bên phải thanh toán cho nhau phần chênh lệch đó, trừ trường hợp có thỏa thuận khác hoặc pháp luật có quy định khác."
- **overlap:** 0,25 — **viết lại:** 0 lần

## 18. boluat-danssu.pdf › Chương XVI › MỘT SỐ HỢP ĐỒNG THÔNG DỤNG › Mục 7. HỢP ĐỒNG VỀ QUYỀN SỬ DỤNG ĐẤT › Điều 502. Hình thức, thủ tục thực hiện hợp đồng về quyền sử dụng đất
- **Câu hỏi:** Khi mua bán, chuyển nhượng đất, giấy tờ giao dịch có bắt buộc phải làm bằng văn bản không?
- **Trích dẫn (nguyên văn trong chunk):** "Hợp đồng về quyền sử dụng đất phải được lập thành văn bản theo hình thức phù hợp với quy định của Bộ luật này, pháp luật về đất đai và quy định khác của pháp luật có liên quan."
- **overlap:** 0,07 — **viết lại:** 0 lần

## 19. boluat-danssu.pdf › Chương XX › TRÁCH NHIỆM BỒI THƯỜNG THIỆT HẠI NGOÀI HỢP ĐỒNG › Mục 1. QUY ĐỊNH CHUNG › Điều 586. Năng lực chịu trách nhiệm bồi thường thiệt hại của cá nhân
- **Câu hỏi:** Một người 16 tuổi lỡ làm hỏng đồ hoặc gây tổn thất cho người khác thì ai phải đứng ra đền bù, người đó hay cha mẹ?
- **Trích dẫn (nguyên văn trong chunk):** "Người từ đủ mười lăm tuổi đến chưa đủ mười tám tuổi gây thiệt hại thì phải bồi thường bằng tài sản của mình; nếu không đủ tài sản để bồi thường thì cha, mẹ phải bồi thường phần còn thiếu bằng tài sản của mình."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 20. boluat-danssu.pdf › Chương XXII › THỪA KẾ THEO DI CHÚC › Điều 648. Giải thích nội dung di chúc
- **Câu hỏi:** Nếu một văn bản để lại tài sản của người đã qua đời có chỗ viết mập mờ khiến những người thừa kế hiểu theo nhiều cách khác nhau, phải xử lý sao?
- **Trích dẫn (nguyên văn trong chunk):** "Khi những người này không nhất trí về cách hiểu nội dung di chúc thì có quyền yêu cầu Tòa án giải quyết."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 21. boluat-danssu.pdf › NHỮNG QUY ĐỊNH CHUNG › Điều 5. Áp dụng tập quán
- **Câu hỏi:** Khi luật và hợp đồng đều không quy định, có được dùng thói quen địa phương lâu đời để giải quyết tranh chấp dân sự không?
- **Trích dẫn (nguyên văn trong chunk):** "Trường hợp các bên không có thỏa thuận và pháp luật không quy định thì có thể áp dụng tập quán nhưng tập quán áp dụng không được trái với các nguyên tắc cơ bản của pháp luật dân sự quy định tại Điều 3 của Bộ luật này."
- **overlap:** 0,20 — **viết lại:** 0 lần

## 22. boluat-thuongmai.pdf › Chương II › MỤC 2. QUYỀN VÀ NGHĨA VỤ CỦA CÁC BÊN TRONG HỢP ĐỒNG MUA BÁN HÀNG HÓA › Điều 42. Giao chứng từ liên quan đến hàng hoá
- **Câu hỏi:** Nếu hợp đồng mua bán không nói rõ khi nào phải nộp giấy tờ đi kèm lô hàng, bên bán phải nộp trong thời gian nào?
- **Trích dẫn (nguyên văn trong chunk):** "Trường hợp không có thỏa thuận về thời hạn, địa điểm giao chứng từ liên quan đến hàng hoá cho bên mua thì bên bán phải giao chứng từ liên quan đến hàng hoá cho bên mua trong thời hạn và tại địa điểm hợp lý để bên mua có thể nhận hàng."
- **overlap:** 0,10 — **viết lại:** 0 lần

## 23. boluat-thuongmai.pdf › Chương IV › MỤC 2. QUẢNG CÁO THƯƠNG MẠI › Điều 102. Quảng cáo thương mại
- **Câu hỏi:** Việc một công ty đăng tin giới thiệu hàng hóa, dịch vụ của mình để thu hút khách mua gọi là loại hoạt động gì?
- **Trích dẫn (nguyên văn trong chunk):** "Quảng cáo thương mại là hoạt động xúc tiến thương mại của thương nhân để giới thiệu với khách hàng về hoạt động kinh doanh hàng hoá, dịch vụ của mình."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 24. boluat-thuongmai.pdf › Chương IV › XÚC TIẾN THƯƠNG MẠI › Điều 93. Hàng hóa, dịch vụ được khuyến mại
- **Câu hỏi:** Có được tặng kèm, giảm giá để câu khách đối với những mặt hàng bị cấm kinh doanh không?
- **Trích dẫn (nguyên văn trong chunk):** "Hàng hóa, dịch vụ được khuyến mại phải là hàng hóa, dịch vụ được kinh doanh hợp pháp."
- **overlap:** 0,22 — **viết lại:** 0 lần

## 25. boluat-thuongmai.pdf › Chương VI › MỘT SỐ HOẠT ĐỘNG THƯƠNG MẠI CỤ THỂ KHÁC › Điều 178. Gia công trong thương mại
- **Câu hỏi:** Khi một xưởng nhận nguyên liệu của khách để làm ra sản phẩm theo yêu cầu rồi lấy tiền công, việc đó gọi là hoạt động gì trong kinh doanh?
- **Trích dẫn (nguyên văn trong chunk):** "Gia công trong thương mại là hoạt động thương mại, theo đó bên nhận gia công sử dụng một phần hoặc toàn bộ nguyên liệu, vật liệu của bên đặt gia công để thực hiện một hoặc nhiều công đoạn trong quá trình sản xuất theo yêu cầu của bên đặt gia công để hưởng thù lao."
- **overlap:** 0,29 — **viết lại:** 0 lần

## 26. boluat-thuongmai.pdf › Chương VI › MỤC 3. ĐẤU THẦU HÀNG HÓA, DỊCH VỤ › Điều 225. Xét hồ sơ dự thầu khi mở thầu
- **Câu hỏi:** Khi các đơn vị nộp đề xuất tham gia một gói mua sắm, bên tổ chức có quyền yêu cầu làm rõ những phần chưa rõ ràng trong đề xuất đó không? Nếu có thì cần lập bằng hình thức gì?
- **Trích dẫn (nguyên văn trong chunk):** "Việc yêu cầu và giải thích hồ sơ dự thầu phải được lập thành văn bản."
- **overlap:** 0,11 — **viết lại:** 0 lần

## 27. boluat-thuongmai.pdf › Chương VI › MỤC 7. CHO THUÊ HÀNG HÓA › Điều 272. Sửa chữa, thay đổi tình trạng ban đầu của hàng hóa cho thuê
- **Câu hỏi:** Người đang thuê một món đồ có được tự ý cải tạo hay làm khác đi so với lúc nhận không?
- **Trích dẫn (nguyên văn trong chunk):** "Bên thuê không được sửa chữa, thay đổi tình trạng ban đầu của hàng hóa cho thuê nếu không được bên cho thuê chấp thuận."
- **overlap:** 0,07 — **viết lại:** 0 lần

## 28. boluat-thuongmai.pdf › Chương VII › MỤC 2. GIẢI QUYẾT TRANH CHẤP TRONG THƯƠNG MẠI › Điều 319. Thời hiệu khởi kiện
- **Câu hỏi:** Doanh nghiệp có tối đa bao lâu để kiện đối tác ra tòa kể từ khi quyền lợi của mình trong một vụ tranh chấp mua bán bị xâm phạm?
- **Trích dẫn (nguyên văn trong chunk):** "Thời hiệu khởi kiện áp dụng đối với các tranh chấp thương mại là hai năm, kể từ thời điểm quyền và lợi ích hợp pháp bị xâm phạm, trừ trường hợp quy định tại điểm e khoản 1 Điều 237 của Luật này."
- **overlap:** 0,17 — **viết lại:** 0 lần

## 29. boluat-laodong.pdf › Chương III › HỢP ĐỒNG LAO ĐỘNG › Mục 4. HỢP ĐỒNG LAO ĐỘNG VÔ HIỆU › Điều 51. Xử lý hợp đồng lao động vô hiệu
- **Câu hỏi:** Nếu hợp đồng làm việc của một nhân viên bị tuyên là không có giá trị pháp lý ngay từ đầu, quyền lợi của người đó được giải quyết theo đâu?
- **Trích dẫn (nguyên văn trong chunk):** "Khi hợp đồng lao động bị tuyên bố vô hiệu toàn bộ thì quyền, nghĩa vụ và lợi ích của người lao động được giải quyết theo quy định của pháp luật; trường hợp do ký sai thẩm quyền thì hai bên ký lại."
- **overlap:** 0,33 — **viết lại:** 0 lần

## 30. boluat-laodong.pdf › Chương VI › TIỀN LƯƠNG › Điều 98. Tiền lương làm thêm giờ, làm việc vào ban đêm
- **Câu hỏi:** Nhân viên đi làm vào ngày nghỉ lễ, tết được trả thêm ít nhất bao nhiêu phần trăm so với lương ngày thường?
- **Trích dẫn (nguyên văn trong chunk):** "c) Vào ngày nghỉ lễ, tết, ngày nghỉ có hưởng lương, ít nhất bằng 300% chưa kể tiền lương ngày lễ, tết, ngày nghỉ có hưởng lương đối với người lao động hưởng lương ngày."
- **overlap:** 0,36 — **viết lại:** 0 lần

## 31. boluat-laodong.pdf › Chương XI › NHỮNG QUY ĐỊNH RIÊNG ĐỐI VỚI LAO ĐỘNG CHƯA THÀNH NIÊN VÀ MỘT SỐ LAO ĐỘNG KHÁC › Mục 5. LAO ĐỘNG LÀ NGƯỜI GIÚP VIỆC GIA ĐÌNH › Điều 161. Lao động là người giúp việc gia đình
- **Câu hỏi:** Nếu một ai đó được một hộ dân thuê thường xuyên để nấu ăn, dọn dẹp, chăm trẻ nhỏ hoặc chăm sóc các cụ già trong nhà, sự thuê mướn này có được pháp luật xem là một dạng cần bảo vệ riêng không?
- **Trích dẫn (nguyên văn trong chunk):** "Các công việc trong gia đình bao gồm công việc nội trợ, quản gia, chăm sóc trẻ em, chăm sóc người bệnh, chăm sóc người già, lái xe, làm vườn và các công việc khác cho hộ gia đình nhưng không liên quan đến hoạt động thương mại."
- **overlap:** 0,20 — **viết lại:** 1 lần

## 32. boluat-laodong.pdf › Chương XVI › THANH TRA LAO ĐỘNG, XỬ LÝ VI PHẠM PHÁP LUẬT VỀ LAO ĐỘNG › Điều 216. Quyền của thanh tra lao động
- **Câu hỏi:** Đoàn kiểm tra an toàn lao động có phải báo trước cho công ty khi đến kiểm tra đột xuất vì lý do khẩn cấp đe dọa tính mạng công nhân không?
- **Trích dẫn (nguyên văn trong chunk):** "Khi thanh tra đột xuất theo quyết định của người có thẩm quyền trong trường hợp khẩn cấp có nguy cơ đe dọa an toàn, tính mạng, sức khỏe, danh dự, nhân phẩm của người lao động tại nơi làm việc thì không cần báo trước."
- **overlap:** 0,38 — **viết lại:** 0 lần

## 33. luat-doanhnghiep.pdf › Chương III › CÔNG TY TRÁCH NHIỆM HỮU HẠN › Mục 1. CÔNG TY TRÁCH NHIỆM HỮU HẠN HAI THÀNH VIÊN TRỞ LÊN › Điều 51. Mua lại phần vốn góp
- **Câu hỏi:** Nếu một thành viên công ty TNHH không đồng ý với quyết định tổ chức lại công ty, thành viên đó có quyền yêu cầu công ty hoàn lại khoản tiền đã đầu tư vào công ty không? Nếu có, phải gửi yêu cầu trong thời hạn bao lâu?
- **Trích dẫn (nguyên văn trong chunk):** "Yêu cầu mua lại phần vốn góp phải bằng văn bản và được gửi đến công ty trong thời hạn 15 ngày kể từ ngày thông qua nghị quyết, quyết định quy định tại khoản 1 Điều này."
- **overlap:** 0,14 — **viết lại:** 0 lần

## 34. luat-doanhnghiep.pdf › Chương IV › DOANH NGHIỆP NHÀ NƯỚC › Điều 94. Miễn nhiệm, cách chức thành viên Hội đồng thành viên
- **Câu hỏi:** Sau khi một người trong ban lãnh đạo công ty nhà nước bị buộc thôi chức, công ty có bao lâu để chọn người thay thế?
- **Trích dẫn (nguyên văn trong chunk):** "Trong thời hạn 60 ngày kể từ ngày có quyết định miễn nhiệm hoặc cách chức Chủ tịch và thành viên khác của Hội đồng thành viên, cơ quan đại diện chủ sở hữu xem xét, quyết định tuyển chọn, bổ nhiệm người khác thay thế."
- **overlap:** 0,10 — **viết lại:** 0 lần

## 35. luat-doanhnghiep.pdf › Chương V › CÔNG TY CỔ PHẦN › Điều 143. Mời họp Đại hội đồng cổ đông
- **Câu hỏi:** Công ty cổ phần phải gửi thông báo cho cổ đông về cuộc họp thường niên trước tối thiểu bao nhiêu ngày?
- **Trích dẫn (nguyên văn trong chunk):** "Người triệu tập họp Đại hội đồng cổ đông phải gửi thông báo mời họp đến tất cả cổ đông trong danh sách cổ đông có quyền dự họp chậm nhất là 21 ngày trước ngày khai mạc nếu Điều lệ công ty không quy định thời hạn dài hơn."
- **overlap:** 0,38 — **viết lại:** 0 lần

## 36. luat-doanhnghiep.pdf › Chương VIII › NHÓM CÔNG TY › Điều 197. Báo cáo tài chính của công ty mẹ, công ty con
- **Câu hỏi:** Vào cuối năm tài chính, tập đoàn có đơn vị trực thuộc phải lập thêm những loại tài liệu tổng hợp nào ngoài báo cáo thông thường?
- **Trích dẫn (nguyên văn trong chunk):** "Vào thời điểm kết thúc năm tài chính, ngoài báo cáo và tài liệu theo quy định của pháp luật, công ty mẹ còn phải lập các báo cáo sau đây: a) Báo cáo tài chính hợp nhất của công ty mẹ theo quy định của pháp luật về kế toán; b) Báo cáo tổng hợp kết quả kinh doanh hằng năm của công ty mẹ và công ty con; c) Báo cáo tổng hợp công tác quản lý, điều hành của công ty mẹ và công ty con."
- **overlap:** 0,36 — **viết lại:** 0 lần

## 37. luat-quanlythue.pdf › Chương IV › KHAI THUẾ, TÍNH THUẾ › Điều 47. Khai bổ sung hồ sơ khai thuế
- **Câu hỏi:** Nếu phát hiện tờ khai nộp thuế trước đây bị sai, doanh nghiệp có tối đa bao lâu để sửa lại trước khi bị thanh tra?
- **Trích dẫn (nguyên văn trong chunk):** "Người nộp thuế phát hiện hồ sơ khai thuế đã nộp cho cơ quan thuế có sai, sót thì được khai bổ sung hồ sơ khai thuế trong thời hạn 10 năm kể từ ngày hết thời hạn nộp hồ sơ khai thuế của kỳ tính thuế có sai, sót nhưng trước khi cơ quan thuế, cơ quan có thẩm quyền công bố quyết định thanh tra, kiểm tra."
- **overlap:** 0,25 — **viết lại:** 0 lần

## 38. luat-quanlythue.pdf › Chương XI › THÔNG TIN NGƯỜI NỘP THUẾ › Điều 97. Trách nhiệm của người nộp thuế trong việc cung cấp thông tin
- **Câu hỏi:** Người đóng thuế có bắt buộc phải chia sẻ đầy đủ và trung thực dữ liệu liên quan cho cơ quan thuế khi được yêu cầu không?
- **Trích dẫn (nguyên văn trong chunk):** "Cung cấp đầy đủ, chính xác, trung thực, đúng thời hạn thông tin trong hồ sơ thuế, thông tin liên quan đến việc xác định nghĩa vụ thuế theo yêu cầu của cơ quan quản lý thuế."
- **overlap:** 0,14 — **viết lại:** 0 lần

## 39. luat-quanlythue.pdf › Chương XVI › KHIẾU NẠI, TỐ CÁO, KHỞI KIỆN › Điều 149. Trách nhiệm và quyền hạn của cơ quan quản lý thuế trong việc giải quyết khiếu nại về thuế
- **Câu hỏi:** Nếu cơ quan thuế thu nhầm tiền phạt của doanh nghiệp, họ phải hoàn trả lại trong bao nhiêu ngày kể từ khi có quyết định xử lý?
- **Trích dẫn (nguyên văn trong chunk):** "Cơ quan quản lý thuế phải hoàn trả số tiền thuế, tiền chậm nộp, tiền phạt thu không đúng cho người nộp thuế, bên thứ ba trong thời hạn 15 ngày kể từ ngày nhận được quyết định xử lý của cơ quan có thẩm quyền."
- **overlap:** 0,37 — **viết lại:** 0 lần

## 40. luat-baohiemxahoi.pdf › Chương IX › KHIẾU NẠI, TỐ CÁO VÀ XỬ LÝ VI PHẠM VỀ BẢO HIỂM XÃ HỘI › Điều 130. Khiếu nại và giải quyết khiếu nại đối với quyết định, hành vi về bảo hiểm xã hội
- **Câu hỏi:** Nếu người lao động không đồng ý với cách cơ quan BHXH xử lý lần đầu về một quyết định liên quan đến chế độ của mình, họ có những lựa chọn nào tiếp theo?
- **Trích dẫn (nguyên văn trong chunk):** "Trường hợp người khiếu nại không đồng ý với quyết định giải quyết khiếu nại lần đầu hoặc hết thời hạn quy định mà khiếu nại không được giải quyết thì có quyền khiếu nại lần hai đến Thủ trưởng cơ quan bảo hiểm xã hội cấp trên trực tiếp của người có thẩm quyền giải quyết khiếu nại lần đầu hoặc khởi kiện tại Tòa án theo quy định của pháp luật."
- **overlap:** 0,24 — **viết lại:** 0 lần

## 41. luat-baohiemxahoi.pdf › Chương V › BẢO HIỂM XÃ HỘI BẮT BUỘC › Mục 4. CHẾ ĐỘ TỬ TUẤT › Điều 86. Các trường hợp hưởng trợ cấp tuất hằng tháng
- **Câu hỏi:** Nếu một người đã đóng bảo hiểm xã hội từ đủ 15 năm trở lên rồi qua đời, thân nhân của họ có được nhận khoản hỗ trợ định kỳ hằng tháng không?
- **Trích dẫn (nguyên văn trong chunk):** "Có thời gian đóng bảo hiểm xã hội bắt buộc từ đủ 15 năm trở lên"
- **overlap:** 0,27 — **viết lại:** 0 lần

## 42. luat-baohiemxahoi.pdf › Chương X › QUẢN LÝ NHÀ NƯỚC VỀ BẢO HIỂM XÃ HỘI › Điều 138. Trách nhiệm của Ủy ban nhân dân các cấp
- **Câu hỏi:** Chính quyền địa phương có phải chỉ đạo và kiểm tra việc thực hiện chính sách bảo hiểm xã hội tại tỉnh mình không?
- **Trích dẫn (nguyên văn trong chunk):** "Ủy ban nhân dân cấp tỉnh chịu trách nhiệm trước Hội đồng nhân dân cùng cấp trong việc chỉ đạo, tổ chức thực hiện chính sách bảo hiểm xã hội, phát triển đối tượng tham gia bảo hiểm xã hội bắt buộc, bảo hiểm xã hội tự nguyện và chậm đóng bảo hiểm xã hội bắt buộc, trốn đóng bảo hiểm xã hội bắt buộc trong phạm vi địa phương."
- **overlap:** 0,00 — **viết lại:** 0 lần

## 43. luat-dautu.pdf › Chương VII › PHỤ LỤC IV
- **Câu hỏi:** Kinh doanh dịch vụ bảo vệ có nằm trong nhóm ngành nghề phải đáp ứng điều kiện riêng mới được làm không?
- **Trích dẫn (nguyên văn trong chunk):** "STT: 10 | NGÀNH, NGHỀ: Kinh doanh dịch vụ bảo vệ"
- **overlap:** 0,00 — **viết lại:** 0 lần

## 44. luat-thuexuatnhapkhau.pdf › Chương V › ĐIỀU KHOẢN THI HÀNH › Điều 21. Điều khoản chuyển tiếp
- **Câu hỏi:** Một dự án đang được hưởng ưu đãi thuế nhập khẩu cao hơn mức mới quy định thì có bị áp mức thấp hơn khi luật thuế mới có hiệu lực không?
- **Trích dẫn (nguyên văn trong chunk):** "Dự án đang được hưởng ưu đãi về thuế xuất khẩu, thuế nhập khẩu có mức ưu đãi cao hơn mức ưu đãi quy định tại Luật này thì tiếp tục thực hiện theo mức ưu đãi đó cho thời gian hưởng ưu đãi còn lại của dự án"
- **overlap:** 0,00 — **viết lại:** 0 lần

## 45. luat-thuegtgt.pdf › Chương IV › ĐIỀU KHOẢN THI HÀNH › Điều 17. Sửa đổi, bổ sung khoản 1 Điều 3 của Luật Thuế thu nhập cá nhân số 04/2007/QH12 đã được sửa đổi, bổ sung một số điều theo Luật
- **Câu hỏi:** Thu nhập từ việc một cá nhân có giấy phép hành nghề tự do (như luật sư, kế toán viên) tự làm riêng thì có tính là thu nhập chịu thuế thu nhập cá nhân không?
- **Trích dẫn (nguyên văn trong chunk):** "Thu nhập từ hoạt động hành nghề độc lập của cá nhân có giấy phép hoặc chứng chỉ hành nghề theo quy định của pháp luật."
- **overlap:** 0,32 — **viết lại:** 0 lần

## Nút bỏ

Không có nút nào bị bỏ — 45/45 nút đều viết được câu qua cổng overlap ≤ 0,40 (tối đa 1 lần viết lại mỗi nút, xem ở trên).
