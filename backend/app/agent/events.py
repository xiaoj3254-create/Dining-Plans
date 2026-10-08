from enum import Enum


class TeamEvent(str, Enum):
    UPDATE_DRAFT = "update_draft"
    PUBLISH = "publish"
    JOIN = "join"
    JOIN_BY_LINK = "join_by_link"
    LEAVE = "leave"
    KICK = "kick"
    DISBAND = "disband"
    CLOSE_INVITE = "close_invite"
    AUTO_FORM = "auto_form"
    CHECKIN = "checkin"
    SUBMIT_BILL = "submit_bill"
    AUTO_BILL_LOCK = "auto_bill_lock"
    PAY = "pay"
    AUTO_COMPLETE = "auto_complete"
    ABORT = "abort"
    EXPIRE = "expire"
    FILL_SEAT = "fill_seat"
